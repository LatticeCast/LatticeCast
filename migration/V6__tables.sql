-- upgrade
-- A "table" is a logical user-defined dataset scoped to a workspace.
-- The composite (workspace_id, table_id) is the identity used by every
-- downstream table (rows, table_schemas, table_views).

CREATE TABLE IF NOT EXISTS public.tables (
    workspace_id UUID      NOT NULL,
    table_id     VARCHAR   NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, table_id),
    FOREIGN KEY (workspace_id)
    REFERENCES public.workspaces (workspace_id) ON DELETE CASCADE
);
