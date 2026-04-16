-- upgrade
-- Bootstrap schemas, roles, and login users. Runs as dba_user (superuser
-- created by docker-compose). Replaces the old setup-db.sh script.
--
-- Key: uses `ALTER DEFAULT PRIVILEGES FOR ROLE dba` so ANY future table
-- created by a role in `dba` inherits these grants automatically. No
-- post-hoc regrant migration needed when new tables appear in V3+.

-- ── Schemas ─────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS private;

-- ── Roles (group roles, NOLOGIN) ────────────────────────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dba') THEN
        CREATE ROLE dba;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
        CREATE ROLE app;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_mgr') THEN
        CREATE ROLE login_mgr;
    END IF;
END $$;

-- ── Login users ─────────────────────────────────────────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE USER app_user WITH PASSWORD 'app_pws' IN ROLE app;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_user') THEN
        CREATE USER login_user
        WITH PASSWORD 'login_pws' IN ROLE login_mgr;
    END IF;
END $$;

-- dba_user (the superuser running this migration) joins the `dba` role so
-- `ALTER DEFAULT PRIVILEGES FOR ROLE dba` applies to everything it creates.
GRANT dba TO dba_user;

-- ── app: CRUD on public, SELECT on auth ─────────────────────────────────────
GRANT USAGE ON SCHEMA public TO app;
GRANT USAGE ON SCHEMA auth TO app;

ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA public
GRANT USAGE ON SEQUENCES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT SELECT ON TABLES TO app;

-- ── login_mgr: CRUD on auth only ────────────────────────────────────────────
GRANT USAGE ON SCHEMA auth TO login_mgr;

ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT SELECT, INSERT, UPDATE ON TABLES TO login_mgr;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT USAGE ON SEQUENCES TO login_mgr;
