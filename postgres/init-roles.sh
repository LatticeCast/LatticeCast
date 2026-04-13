#!/bin/bash
set -e

# Create roles and login users with passwords from env vars.
# This script runs inside the postgres container at first boot via
# docker-entrypoint-initdb.d. It must be mounted as a .sh file so that
# shell env var interpolation works for passwords.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	-- Roles (no login)
	CREATE ROLE dba;
	CREATE ROLE app;
	CREATE ROLE login_mgr;

	-- Login users inheriting roles
	CREATE USER dba_user WITH PASSWORD '${POSTGRES_DBA_PASSWORD}' IN ROLE dba;
	CREATE USER app_user WITH PASSWORD '${POSTGRES_APP_PASSWORD}' IN ROLE app;
	CREATE USER login_user WITH PASSWORD '${POSTGRES_LOGIN_PASSWORD}' IN ROLE login_mgr;

	-- DBA: full DDL on current and future objects
	GRANT ALL ON SCHEMA public TO dba;
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO dba;
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO dba;

	-- App: CRUD on future data tables, USAGE on sequences
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO app;

	-- Login manager: SELECT/INSERT/UPDATE on future auth tables
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO login_mgr;
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO login_mgr;
EOSQL
