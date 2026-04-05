-- 0012_users_cleanup.sql
-- Remove email and name from users table — these live in user_info only
-- users table should only have: user_id UUID PK, role, timestamps

ALTER TABLE users DROP COLUMN IF EXISTS email;
ALTER TABLE users DROP COLUMN IF EXISTS name;

-- Drop the old email index if it exists
DROP INDEX IF EXISTS ix_users_email;
