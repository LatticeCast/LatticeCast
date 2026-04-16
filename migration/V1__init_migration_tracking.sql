-- upgrade
-- Initialize migration tracking table. Runs FIRST — all subsequent
-- migrations are recorded here.
--
-- Lives in the `private` schema: DBA-only, hidden from app/login roles.
-- See V2__bootstrap_roles.sql for schema ownership and grants.

CREATE SCHEMA IF NOT EXISTS private;

CREATE TABLE IF NOT EXISTS private.schema_migrations (
    filename   VARCHAR   PRIMARY KEY,
    checksum   VARCHAR   NOT NULL DEFAULT '',
    applied_at TIMESTAMP NOT NULL DEFAULT NOW()
);
