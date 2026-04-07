-- 0020_user_info_user_name_unique.sql
-- Add named UNIQUE constraint on user_info.user_name (matches workspace_name/table_name pattern)

-- Drop any leftover unnamed unique constraint from original display_id column
ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_display_id_key;
ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_user_name_key;
ALTER TABLE user_info DROP CONSTRAINT IF EXISTS uq_user_info_user_name;

-- Add named unique constraint
ALTER TABLE user_info ADD CONSTRAINT uq_user_info_user_name UNIQUE (user_name);
