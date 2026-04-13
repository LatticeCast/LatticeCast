-- 0026_move_users_to_auth_schema.sql
-- task-241: Move users + user_info into auth schema (PG roles restructure)

-- ── Ensure auth schema exists (idempotent) ────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;

-- ── Move tables ───────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS users     SET SCHEMA auth;
ALTER TABLE IF EXISTS user_info SET SCHEMA auth;
