-- upgrade

CREATE TABLE IF NOT EXISTS public.workspaces (
    workspace_id   UUID      NOT NULL DEFAULT gen_random_uuid(),
    workspace_name VARCHAR   NOT NULL DEFAULT '',
    created_at     TIMESTAMP NOT NULL DEFAULT now(),
    updated_at     TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id)
);
