-- upgrade
-- 0008_tables_fk.sql
-- Ensure tables.workspace_id FK references new UUID PK on workspaces(workspace_id).
-- The actual column migration was done in 0006 (Step 5).
-- This migration re-anchors the FK idempotently as a dedicated step for L-81.

-- ── Re-anchor workspace_id FK → workspaces(workspace_id) UUID PK ─────────────

ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_workspace_id_fkey;
ALTER TABLE tables ADD CONSTRAINT tables_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;

-- ── Ensure index on workspace_id ──────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_tables_workspace_id ON tables(workspace_id);
