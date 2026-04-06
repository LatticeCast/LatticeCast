-- 0018_simplify_names.sql
-- Workspace: merge display_id + name → workspace_name (unique)
-- Table: rename name → table_name (unique per workspace)

-- ─── Workspaces: merge display_id + name → workspace_name ────────────────────

-- Add workspace_name (copy from display_id which is the URL-safe slug)
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS workspace_name VARCHAR NOT NULL DEFAULT '';
UPDATE workspaces SET workspace_name = display_id WHERE workspace_name = '';

-- Drop old columns
ALTER TABLE workspaces DROP COLUMN IF EXISTS display_id;
ALTER TABLE workspaces DROP COLUMN IF EXISTS name;

-- Add unique constraint
DROP INDEX IF EXISTS ix_workspaces_display_id;
ALTER TABLE workspaces DROP CONSTRAINT IF EXISTS uq_workspaces_name;
ALTER TABLE workspaces ADD CONSTRAINT uq_workspaces_name UNIQUE (workspace_name);
CREATE INDEX IF NOT EXISTS ix_workspaces_workspace_name ON workspaces(lower(workspace_name));

-- ─── Tables: rename name → table_name, unique per workspace ──────────────────

ALTER TABLE tables RENAME COLUMN name TO table_name;
ALTER TABLE tables DROP CONSTRAINT IF EXISTS uq_tables_workspace_name;
ALTER TABLE tables ADD CONSTRAINT uq_tables_workspace_name UNIQUE (workspace_id, table_name);

-- ─── Drop workspace_info table (no longer needed) ───────────────────────────
DROP TABLE IF EXISTS workspace_info CASCADE;
