-- 0016_workspaces_reorder.sql
-- Reorder workspaces columns: workspace_id first

CREATE TABLE workspaces_new (
    workspace_id UUID NOT NULL DEFAULT gen_random_uuid(),
    display_id   VARCHAR NOT NULL,
    name         VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id)
);

INSERT INTO workspaces_new (workspace_id, display_id, name, created_at, updated_at)
SELECT workspace_id, display_id, name, created_at, updated_at FROM workspaces;

DROP TABLE workspaces CASCADE;
ALTER TABLE workspaces_new RENAME TO workspaces;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS ix_workspaces_display_id ON workspaces(display_id);

-- Recreate FKs
ALTER TABLE tables ADD CONSTRAINT tables_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE workspace_info ADD CONSTRAINT workspace_info_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;
