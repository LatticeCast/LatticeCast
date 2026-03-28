-- 0003_workspace_schema.sql
-- Workspace redesign: workspaces, workspace_members, migrate columns to JSONB, rename PKs

-- 1. Create workspaces table
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 2. Create workspace_members table
CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id      VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role         VARCHAR NOT NULL DEFAULT 'member',
    PRIMARY KEY (workspace_id, user_id)
);

-- 3. Auto-create default workspace per distinct user_id in tables
INSERT INTO workspaces (workspace_id, name)
SELECT DISTINCT user_id, user_id
FROM tables
ON CONFLICT (workspace_id) DO NOTHING;

-- Also ensure every user in the users table has a default workspace
INSERT INTO workspaces (workspace_id, name)
SELECT user_id, user_id
FROM users
ON CONFLICT (workspace_id) DO NOTHING;

-- 4. Populate workspace_members (all existing users are owners of their default workspace)
INSERT INTO workspace_members (workspace_id, user_id, role)
SELECT user_id, user_id, 'owner'
FROM users
ON CONFLICT (workspace_id, user_id) DO NOTHING;

-- 5. ALTER tables: add workspace_id and columns JSONB
ALTER TABLE tables
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR REFERENCES workspaces(workspace_id),
    ADD COLUMN IF NOT EXISTS columns      JSONB NOT NULL DEFAULT '[]';

-- 6. Migrate tables.workspace_id from tables.user_id
UPDATE tables SET workspace_id = user_id WHERE workspace_id IS NULL;

-- 7. Migrate column definitions from columns table into tables.columns JSONB array
UPDATE tables t
SET columns = (
    SELECT COALESCE(
        json_agg(
            json_build_object(
                'column_id', c.id::text,
                'name',      c.name,
                'type',      c.type,
                'options',   c.options,
                'position',  c.position
            )
            ORDER BY c.position
        )::jsonb,
        '[]'::jsonb
    )
    FROM columns c
    WHERE c.table_id = t.id
);

-- 8. Make workspace_id NOT NULL now that data is populated
ALTER TABLE tables
    ALTER COLUMN workspace_id SET NOT NULL;

-- 9. Drop user_id from tables (replaced by workspace_id)
ALTER TABLE tables DROP COLUMN IF EXISTS user_id;

-- 10. Rename tables.id → table_id
ALTER TABLE tables RENAME COLUMN id TO table_id;

-- 11. ALTER rows: rename id→row_id, data→row_data, add created_by/updated_by
ALTER TABLE rows RENAME COLUMN id TO row_id;
ALTER TABLE rows RENAME COLUMN data TO row_data;
ALTER TABLE rows
    ADD COLUMN IF NOT EXISTS created_by VARCHAR NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS updated_by VARCHAR NOT NULL DEFAULT '';

-- 12. Drop old GIN index on data (column renamed), recreate not needed per design notes
DROP INDEX IF EXISTS idx_rows_data;

-- 13. Drop the columns table (definitions now live in tables.columns JSONB)
DROP TABLE IF EXISTS columns;

-- 14. Drop old indexes that referenced renamed/dropped columns
DROP INDEX IF EXISTS idx_columns_table_id;
DROP INDEX IF EXISTS idx_tables_user_id;

-- 15. Create new indexes
CREATE INDEX IF NOT EXISTS idx_rows_table_id         ON rows(table_id);
CREATE INDEX IF NOT EXISTS idx_tables_workspace_id   ON tables(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);
