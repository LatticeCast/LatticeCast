-- upgrade

CREATE TABLE IF NOT EXISTS public.workspace_members (
    workspace_id UUID    NOT NULL,
    user_id      UUID    NOT NULL,
    role         VARCHAR NOT NULL DEFAULT 'member',
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id)
    REFERENCES public.workspaces (workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)
    REFERENCES auth.users (user_id) ON DELETE CASCADE
);
