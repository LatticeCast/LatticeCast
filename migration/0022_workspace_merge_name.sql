-- 0017_workspace_merge_name.sql
-- Merge display_id + name into workspace_name on workspaces, drop workspace_info (redundant)

-- 1. Add workspace_name column (populate from existing name if present)
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS workspace_name VARCHAR NOT NULL DEFAULT '';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workspaces' AND column_name='name') THEN
        UPDATE workspaces SET workspace_name = name WHERE workspace_name = '';
    END IF;
END
$$;

-- 2. Drop display_id and name columns (merged into workspace_name)
ALTER TABLE workspaces DROP COLUMN IF EXISTS display_id;
ALTER TABLE workspaces DROP COLUMN IF EXISTS name;

-- 3. Drop workspace_info table (was just a duplicate of workspaces.display_id + name)
DROP TABLE IF EXISTS workspace_info CASCADE;

-- 4. Index on workspace_name for fast case-insensitive lookup
CREATE INDEX IF NOT EXISTS ix_workspaces_workspace_name ON workspaces(LOWER(workspace_name));
