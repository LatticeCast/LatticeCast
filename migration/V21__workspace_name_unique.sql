-- upgrade
-- workspace_name must be unique — the BE route (POST /workspaces)
-- catches IntegrityError for 409 but the constraint was missing.

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_workspaces_name_unique
    ON public.workspaces (workspace_name);
