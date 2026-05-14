-- upgrade
-- Make the role separation from V1 actually work at runtime.
--
-- Two issues V1 leaves open and this migration fixes:
--
-- 1. ALTER DEFAULT PRIVILEGES FOR ROLE dba only applies to objects CREATED
--    BY the dba role. Our migration runner connects as dba_user (a login
--    user that INHERITS the dba group). Tables are owned by dba_user, not
--    by dba, so the default-priv machinery silently skips them — leaving
--    app/mgr with USAGE on schemas but no DML on tables.
--
-- 2. PG role attributes (BYPASSRLS, SUPERUSER, LOGIN, …) are NOT inherited
--    through GRANT mgr TO mgr_user. The mgr group has BYPASSRLS from V1,
--    but the actual session role is mgr_user. mgr_user must have the
--    attribute set explicitly.
--
-- Together these grants + the BYPASSRLS attribute let:
--   - app_user CRUD on public + read auth + self-row gdpr (RLS narrows)
--   - mgr_user CRUD everywhere with no RLS (login + admin bootstrap)

-- ── app role: table-level grants ────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app;

GRANT SELECT ON ALL TABLES IN SCHEMA auth TO app;

GRANT SELECT, UPDATE ON ALL TABLES IN SCHEMA gdpr TO app;

-- ── mgr role: table-level grants ────────────────────────────────────────────
-- Belt and braces: re-grant so a fresh DB works even if the default-priv
-- mechanism is bypassed for whatever reason.

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO mgr;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA auth TO mgr;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA gdpr TO mgr;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mgr;

-- ── mgr_user: BYPASSRLS attribute ───────────────────────────────────────────
-- Required so the login session (auth lookups before any user is
-- authenticated, admin bootstrap flows) can see all rows. App session
-- still goes through RLS normally.

ALTER ROLE mgr_user BYPASSRLS;
