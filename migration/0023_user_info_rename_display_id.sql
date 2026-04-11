-- 0019_user_info_rename_display_id.sql
-- Rename user_info.display_id → user_name (UNIQUE)

-- ── 1. Drop old index ─────────────────────────────────────────────────────────

DROP INDEX IF EXISTS ix_user_info_display_id;

-- ── 2. Rename column ──────────────────────────────────────────────────────────

ALTER TABLE user_info RENAME COLUMN display_id TO user_name;

-- ── 3. Recreate index with new name ───────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_user_info_user_name ON user_info(user_name);
