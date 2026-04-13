#!/bin/bash
# postgres/init-roles.sh
# Creates schemas, roles, login users, and grants.
# Runs once at container init via docker-entrypoint-initdb.d.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  -- ── Schemas ──────────────────────────────────────────────────────────────────
  CREATE SCHEMA IF NOT EXISTS auth;
  CREATE SCHEMA IF NOT EXISTS private;

  -- ── Roles ────────────────────────────────────────────────────────────────────
  DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dba') THEN
      CREATE ROLE dba;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
      CREATE ROLE app;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_mgr') THEN
      CREATE ROLE login_mgr;
    END IF;
  END \$\$;

  -- ── Login users ───────────────────────────────────────────────────────────────
  DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dba_user') THEN
      CREATE USER dba_user WITH PASSWORD '${POSTGRES_DBA_PASSWORD}' IN ROLE dba;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
      CREATE USER app_user WITH PASSWORD '${POSTGRES_APP_PASSWORD}' IN ROLE app;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'login_user') THEN
      CREATE USER login_user WITH PASSWORD '${POSTGRES_LOGIN_PASSWORD}' IN ROLE login_mgr;
    END IF;
  END \$\$;

  -- ── DBA: full access on all schemas ──────────────────────────────────────────
  ALTER ROLE dba BYPASSRLS;
  GRANT ALL ON SCHEMA public, auth, private TO dba;
  GRANT ALL ON ALL TABLES    IN SCHEMA public  TO dba;
  GRANT ALL ON ALL TABLES    IN SCHEMA auth    TO dba;
  GRANT ALL ON ALL TABLES    IN SCHEMA private TO dba;
  GRANT ALL ON ALL SEQUENCES IN SCHEMA public  TO dba;
  GRANT ALL ON ALL SEQUENCES IN SCHEMA auth    TO dba;
  GRANT ALL ON ALL SEQUENCES IN SCHEMA private TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public  GRANT ALL ON TABLES    TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA auth    GRANT ALL ON TABLES    TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA private GRANT ALL ON TABLES    TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public  GRANT ALL ON SEQUENCES TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA auth    GRANT ALL ON SEQUENCES TO dba;
  ALTER DEFAULT PRIVILEGES IN SCHEMA private GRANT ALL ON SEQUENCES TO dba;

  -- ── App: CRUD on public, SELECT on auth ───────────────────────────────────────
  GRANT USAGE ON SCHEMA public TO app;
  GRANT USAGE ON SCHEMA auth   TO app;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA public TO app;
  GRANT USAGE                          ON ALL SEQUENCES IN SCHEMA public TO app;
  GRANT SELECT                         ON ALL TABLES    IN SCHEMA auth   TO app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE                          ON SEQUENCES TO app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA auth   GRANT SELECT                         ON TABLES    TO app;

  -- ── Login manager: CRUD on auth only ─────────────────────────────────────────
  GRANT USAGE ON SCHEMA auth TO login_mgr;
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA auth TO login_mgr;
  GRANT USAGE                  ON ALL SEQUENCES IN SCHEMA auth TO login_mgr;
  ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT SELECT, INSERT, UPDATE ON TABLES    TO login_mgr;
  ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT USAGE                  ON SEQUENCES TO login_mgr;
EOSQL
