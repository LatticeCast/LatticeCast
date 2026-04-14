-- upgrade
-- 0002_create_tables_schema.sql
-- Workspace-based schema: workspaces, tables (columns JSONB), rows (row_data JSONB)
-- Users table: email is the unique identity across all login methods

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR PRIMARY KEY,  -- email address (same user regardless of login method)
    name VARCHAR NOT NULL DEFAULT '',
    role VARCHAR NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

-- Seed admin users via scripts/dev_seed.sql (not in migration)


CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id      VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role         VARCHAR NOT NULL DEFAULT 'member',
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS tables (
    table_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  VARCHAR NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    name          VARCHAR NOT NULL,
    columns       JSONB NOT NULL DEFAULT '[]',
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rows (
    row_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id    UUID NOT NULL REFERENCES tables(table_id) ON DELETE CASCADE,
    row_data    JSONB NOT NULL DEFAULT '{}',
    created_by  VARCHAR NOT NULL DEFAULT '',
    updated_by  VARCHAR NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rows_table_id ON rows(table_id);
CREATE INDEX IF NOT EXISTS idx_tables_workspace_id ON tables(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);
