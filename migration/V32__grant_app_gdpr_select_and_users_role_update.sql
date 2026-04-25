-- upgrade
-- V32: Grant app SELECT on auth.gdpr and UPDATE(role) on auth.users.
-- Restricts login_mgr to register/delete only; app handles all auth lookups.
-- auth.gdpr was created in V10 with login_mgr-only grants; app never received SELECT.
-- auth.users had only SELECT granted to app in V26; UPDATE(role) is added here.

GRANT SELECT ON auth.gdpr TO app;
GRANT UPDATE (role) ON auth.users TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE dba IN SCHEMA auth
    GRANT SELECT ON TABLES TO app;
