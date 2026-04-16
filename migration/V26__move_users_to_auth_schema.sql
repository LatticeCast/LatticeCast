-- upgrade
-- Move `users` into auth schema. user_info stays in public (public-facing
-- handle + display name). PII (email, legal_name) already lives in auth.gdpr.

CREATE SCHEMA IF NOT EXISTS auth;

-- Drop FKs that reference public.users before the schema move
ALTER TABLE IF EXISTS user_info
DROP CONSTRAINT IF EXISTS user_info_user_id_fkey;
ALTER TABLE IF EXISTS auth.gdpr DROP CONSTRAINT IF EXISTS gdpr_user_id_fkey;
ALTER TABLE IF EXISTS workspace_members
DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;
ALTER TABLE IF EXISTS rows DROP CONSTRAINT IF EXISTS rows_created_by_fkey;
ALTER TABLE IF EXISTS rows DROP CONSTRAINT IF EXISTS rows_updated_by_fkey;

ALTER TABLE IF EXISTS users SET SCHEMA auth;

-- Recreate FKs pointing at auth.users
ALTER TABLE user_info ADD CONSTRAINT user_info_user_id_fkey
FOREIGN KEY (user_id) REFERENCES auth.users (user_id) ON DELETE CASCADE;
ALTER TABLE auth.gdpr ADD CONSTRAINT gdpr_user_id_fkey
FOREIGN KEY (user_id) REFERENCES auth.users (user_id) ON DELETE CASCADE;
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_user_id_fkey
FOREIGN KEY (user_id) REFERENCES auth.users (user_id) ON DELETE CASCADE;
ALTER TABLE rows ADD CONSTRAINT rows_created_by_fkey
FOREIGN KEY (created_by) REFERENCES auth.users (user_id) ON DELETE SET NULL;
ALTER TABLE rows ADD CONSTRAINT rows_updated_by_fkey
FOREIGN KEY (updated_by) REFERENCES auth.users (user_id) ON DELETE SET NULL;

-- ALTER DEFAULT PRIVILEGES does not fire on SET SCHEMA — grant explicitly
GRANT SELECT ON auth.users TO app;
GRANT SELECT, INSERT, UPDATE ON auth.users TO login_mgr;
