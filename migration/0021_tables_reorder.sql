-- 0021_tables_reorder.sql
-- Reorder tables columns: workspace_id, table_id, table_name, columns, views, created_at, updated_at

CREATE TABLE tables_new (
    workspace_id UUID        NOT NULL,
    table_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
    table_name   VARCHAR     NOT NULL,
    columns      JSONB       NOT NULL DEFAULT '[]',
    views        JSONB       NOT NULL DEFAULT '[]',
    created_at   TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (table_id)
);

INSERT INTO tables_new (workspace_id, table_id, table_name, columns, views, created_at, updated_at)
SELECT workspace_id, table_id, table_name, columns, views, created_at, updated_at FROM tables;

-- Drop old table (CASCADE drops rows_table_id_fkey and other dependent constraints)
DROP TABLE tables CASCADE;
ALTER TABLE tables_new RENAME TO tables;

-- Recreate FK: tables → workspaces
ALTER TABLE tables ADD CONSTRAINT tables_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;

-- Recreate unique constraint: table_name unique within workspace
ALTER TABLE tables ADD CONSTRAINT uq_tables_workspace_name UNIQUE (workspace_id, table_name);

-- Recreate index on workspace_id
CREATE INDEX IF NOT EXISTS idx_tables_workspace_id ON tables(workspace_id);

-- Recreate FK: rows → tables
ALTER TABLE rows ADD CONSTRAINT rows_table_id_fkey
    FOREIGN KEY (table_id) REFERENCES tables(table_id) ON DELETE CASCADE;
