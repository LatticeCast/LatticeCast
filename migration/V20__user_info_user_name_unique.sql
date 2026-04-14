-- upgrade
-- 0020_user_info_user_name_unique.sql
-- NOTE: user_name UNIQUE constraint moved to 0023 (which renames display_id → user_name)
-- This migration is now a no-op for ordering correctness.

-- Drop any leftover unnamed unique constraint from original display_id column
ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_display_id_key;
