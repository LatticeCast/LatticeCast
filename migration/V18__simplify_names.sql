-- upgrade
-- 0018_simplify_names.sql
-- Tables: rename name → table_name, unique per workspace
-- Drop workspace_info (cleanup)
-- NOTE: workspace_name UNIQUE constraint moved to 0022 (which creates the
-- column)

-- Only rename if column "name" still exists (idempotent)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tables' AND column_name='name') THEN
    ALTER TABLE tables RENAME COLUMN name TO table_name;
  END IF;
END $$;

-- Unique table_name within same workspace
ALTER TABLE tables DROP CONSTRAINT IF EXISTS uq_tables_workspace_name;
ALTER TABLE tables ADD CONSTRAINT uq_tables_workspace_name UNIQUE (
    workspace_id, table_name
);

-- Drop workspace_info if exists (no longer needed)
DROP TABLE IF EXISTS workspace_info CASCADE;
