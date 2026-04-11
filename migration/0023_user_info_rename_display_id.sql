-- 0023_user_info_rename_display_id.sql
-- Rename user_info.display_id → user_name (idempotent)

DROP INDEX IF EXISTS ix_user_info_display_id;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_info' AND column_name='display_id') THEN
    ALTER TABLE user_info RENAME COLUMN display_id TO user_name;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_user_info_user_name ON user_info(user_name);
