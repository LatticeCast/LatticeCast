-- upgrade
-- V32: Grant app SELECT on auth.gdpr and UPDATE(role) on auth.users.
-- Restricts login_mgr to register/delete only; app handles auth lookups.
-- auth.gdpr (V10) originally had login_mgr-only grants.
-- auth.users (V26) had only SELECT to app; UPDATE(role) added here.

GRANT SELECT ON auth.gdpr TO app;
GRANT UPDATE (role) ON auth.users TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
GRANT SELECT ON TABLES TO app;
