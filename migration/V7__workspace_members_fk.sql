-- upgrade
-- 0007_workspace_members_fk.sql
-- Ensure workspace_members FK columns reference new UUID PKs for both workspace_id and user_id.
-- The actual column migrations were done in 0005 (user_id) and 0006 (workspace_id).
-- This migration verifies and ensures the final correct FK state idempotently.

-- ── Re-anchor workspace_id FK → workspaces(workspace_id) UUID PK ─────────────

ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_workspace_id_fkey;
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;

-- ── Re-anchor user_id FK → users(user_id) UUID PK ────────────────────────────

ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

-- ── Ensure index on user_id ───────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);
