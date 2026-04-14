-- upgrade
-- Re-grant permissions on all existing tables.
-- V1 grants ON ALL TABLES only covers tables that existed at grant time.
-- Tables created by later migrations (e.g. user_info in V10) were missed.

-- App: CRUD on public, SELECT on auth
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app;
GRANT SELECT ON ALL TABLES IN SCHEMA auth TO app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA auth TO app;

-- Login manager: CRUD on auth
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA auth TO login_mgr;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA auth TO login_mgr;
