-- upgrade
-- Bootstrap: schemas, roles, login users, default privileges, migration
-- tracking table. Runs as the superuser created by docker-compose
-- (POSTGRES_USER=dba_user).
--
-- Roles:
--   dba — DDL (migrations). All schemas.
--   mgr — IT/admin backend. DML on every table; NO DDL (cannot
--         create/alter/drop). BYPASSRLS so admin can see all data.
--   app — end-user session. public CRUD (RLS), gdpr SELECT+UPDATE
--         (own row via RLS), auth SELECT (name resolution).

-- ── Schemas ─────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS gdpr;
CREATE SCHEMA IF NOT EXISTS private;

-- ── Group roles (NOLOGIN) ───────────────────────────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dba') THEN
        CREATE ROLE dba;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mgr') THEN
        CREATE ROLE mgr BYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
        CREATE ROLE app;
    END IF;
END $$;

-- ── Login users (inherit group roles) ───────────────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mgr_user') THEN
        CREATE USER mgr_user IN ROLE mgr;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE USER app_user IN ROLE app;
    END IF;
END $$;

-- dba_user joins dba so ALTER DEFAULT PRIVILEGES FOR ROLE dba applies to
-- everything it creates in later migrations.
GRANT dba TO dba_user;

-- ── dba explicit grants ─────────────────────────────────────────────────────
-- dba is strictly DDL: USAGE+CREATE on every schema, plus DML on the one
-- table it must touch (private.schema_migrations). No grants on data
-- tables — dba cannot SELECT/INSERT/UPDATE/DELETE workspaces, rows, etc.

GRANT USAGE, CREATE ON SCHEMA public  TO dba;
GRANT USAGE, CREATE ON SCHEMA auth    TO dba;
GRANT USAGE, CREATE ON SCHEMA gdpr    TO dba;
GRANT USAGE, CREATE ON SCHEMA private TO dba;

-- ── Schema usage ────────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA public  TO mgr;
GRANT USAGE ON SCHEMA auth    TO mgr;
GRANT USAGE ON SCHEMA gdpr    TO mgr;
GRANT USAGE ON SCHEMA private TO mgr;
GRANT USAGE ON SCHEMA public  TO app;
GRANT USAGE ON SCHEMA auth    TO app;
GRANT USAGE ON SCHEMA gdpr    TO app;

-- ── Default privileges ──────────────────────────────────────────────────────
-- mgr: full DML on every schema (auth + gdpr + public). DDL is implicitly
-- blocked because mgr is not in the dba role.

ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT USAGE ON SEQUENCES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT USAGE ON SEQUENCES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA gdpr
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA gdpr
GRANT USAGE ON SEQUENCES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA private
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA private
GRANT USAGE ON SEQUENCES TO mgr;

-- app: CRUD on public, SELECT on auth, SELECT+UPDATE on gdpr (RLS limits
-- gdpr to the user's own row). app has no access to private.
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT USAGE ON SEQUENCES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT SELECT ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA gdpr
GRANT SELECT, UPDATE ON TABLES TO app;

-- ── search_path per role ────────────────────────────────────────────────────

ALTER ROLE dba SET search_path TO public, auth, gdpr, private;
ALTER ROLE mgr SET search_path TO public, auth, gdpr;
ALTER ROLE app SET search_path TO public, auth, gdpr;

-- ── Migration tracking ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS private.schema_migrations (
    filename   VARCHAR   PRIMARY KEY,
    checksum   VARCHAR   NOT NULL DEFAULT '',
    applied_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Only data-table grant dba needs: tracking its own work.
GRANT SELECT, INSERT, UPDATE ON private.schema_migrations TO dba;
