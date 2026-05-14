-- upgrade
-- POST /workspaces RLS chicken-and-egg fix.
--
-- Problem: the workspaces RLS policy filters by check_workspace_member.
-- For an app_user INSERT, RLS evaluates BEFORE the workspace_members
-- row exists — so the creator is "not a member" and the INSERT is
-- rejected. The login session can't help here because we want the
-- creator's app session (with app.current_user_id set) to own the row.
--
-- Fix: a SECURITY DEFINER PG function that creates both rows in one
-- transaction, running as dba so RLS doesn't gate it. Returns the new
-- workspace.

CREATE OR REPLACE FUNCTION public.create_workspace(
    p_workspace_name VARCHAR,
    p_by UUID
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_workspace_id UUID;
    v_now          TIMESTAMP;
BEGIN
    INSERT INTO public.workspaces (workspace_name)
    VALUES (p_workspace_name)
    RETURNING workspace_id, created_at INTO v_workspace_id, v_now;

    INSERT INTO public.workspace_members (workspace_id, user_id, role)
    VALUES (v_workspace_id, p_by, 'owner');

    RETURN jsonb_build_object(
        'workspace_id',   v_workspace_id,
        'workspace_name', p_workspace_name,
        'created_at',     v_now,
        'updated_at',     v_now
    );
END;
$$;

REVOKE ALL ON FUNCTION public.create_workspace(VARCHAR, UUID) FROM public;
GRANT EXECUTE ON FUNCTION public.create_workspace(VARCHAR, UUID) TO app, mgr;
