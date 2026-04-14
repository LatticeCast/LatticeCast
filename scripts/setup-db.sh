#!/bin/bash
# scripts/setup-db.sh
# One-time bootstrap: connect as pg_init and create schemas, roles, login users, grants.
# Run after: docker compose up -d db
# Idempotent — safe to re-run.
#
# Usage:
#   source .env && docker compose exec db bash -c "$(cat scripts/setup-db.sh)"
# Or directly via psql:
#   PGPASSWORD=pg_init_bootstrap psql -h localhost -U pg_init -d $POSTGRES_DB -f scripts/setup-db.sql
set -e

: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${POSTGRES_DBA_PASSWORD:?POSTGRES_DBA_PASSWORD must be set}"
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD must be set}"
: "${POSTGRES_LOGIN_PASSWORD:?POSTGRES_LOGIN_PASSWORD must be set}"

POSTGRES_HOST="${POSTGRES_URL%%:*}"
POSTGRES_PORT="${POSTGRES_URL##*:}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "Setting up database roles and schemas on ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}..."

PGPASSWORD=pg_init_bootstrap psql \
  -v ON_ERROR_STOP=1 \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U pg_init \
  -d "$POSTGRES_DB" <<-EOSQL
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

echo "Done. Database roles and schemas are set up."
