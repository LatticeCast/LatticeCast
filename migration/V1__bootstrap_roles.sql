-- upgrade
-- 0001_bootstrap_roles.sql
-- Bootstrap schemas, roles, and login users.
-- Runs as dba_user (superuser created by docker-compose).
-- Replaces the old setup-db.sh script.

-- ── Schemas ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS private;

-- ── Roles ────────────────────────────────────────────────────────────────────
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_mgr') THEN
    CREATE ROLE login_mgr;
  END IF;
END $$;

-- ── Login users ──────────────────────────────────────────────────────────────
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE USER app_user WITH PASSWORD 'app_pws' IN ROLE app;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_user') THEN
    CREATE USER login_user WITH PASSWORD 'login_pws' IN ROLE login_mgr;
  END IF;
END $$;

-- ── App: CRUD on public, SELECT on auth ─────────────────────────────────────
GRANT USAGE ON SCHEMA public TO app;
GRANT USAGE ON SCHEMA auth   TO app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA public TO app;
GRANT USAGE                          ON ALL SEQUENCES IN SCHEMA public TO app;
GRANT SELECT                         ON ALL TABLES    IN SCHEMA auth   TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE                          ON SEQUENCES TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth   GRANT SELECT                         ON TABLES    TO app;

-- ── Login manager: CRUD on auth only ────────────────────────────────────────
GRANT USAGE ON SCHEMA auth TO login_mgr;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA auth TO login_mgr;
GRANT USAGE                  ON ALL SEQUENCES IN SCHEMA auth TO login_mgr;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT SELECT, INSERT, UPDATE ON TABLES    TO login_mgr;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT USAGE                  ON SEQUENCES TO login_mgr;
