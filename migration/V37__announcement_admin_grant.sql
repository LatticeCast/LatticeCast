-- V37 — grant bootstrap admins access to the fixed announcement workspace.
--
-- This is deliberately narrower than grant_workspace_action(): callers cannot
-- choose a workspace or access level. It is for the manager-backed admin
-- bootstrap path only and materializes the full owner action set for admins.

CREATE OR REPLACE FUNCTION public.grant_announcement_admin(
    p_user_id UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_workspace_id UUID;
BEGIN
    PERFORM 1
    FROM auth.users
    WHERE user_id = p_user_id
      AND role = 'admin';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'announcement workspace access requires an admin user';
    END IF;

    SELECT workspace_id
    INTO STRICT v_workspace_id
    FROM public.workspaces
    WHERE workspace_name = 'announcement';

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (v_workspace_id, p_user_id, 'read'),
           (v_workspace_id, p_user_id, 'write'),
           (v_workspace_id, p_user_id, 'owner')
    ON CONFLICT (workspace_id, user_id, action) DO NOTHING;
END;
$$;

REVOKE ALL    ON FUNCTION public.grant_announcement_admin(UUID) FROM public;
GRANT EXECUTE ON FUNCTION public.grant_announcement_admin(UUID) TO mgr;
