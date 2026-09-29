-- upgrade
-- V46's effective create_workspace(VARCHAR) predates V60 and retained its
-- returned timestamp in a TIMESTAMP local variable. Keep the offset in its
-- JSONB response as well as in public.workspaces.

CREATE OR REPLACE FUNCTION public.create_workspace(
    p_workspace_name VARCHAR
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_workspace_id UUID;
    v_user_id      UUID;
    v_now          TIMESTAMPTZ;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.workspaces (workspace_name)
    VALUES (p_workspace_name)
    RETURNING workspace_id, created_at INTO v_workspace_id, v_now;

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (v_workspace_id, v_user_id, 'read'),
           (v_workspace_id, v_user_id, 'write'),
           (v_workspace_id, v_user_id, 'owner');

    RETURN jsonb_build_object(
        'workspace_id',   v_workspace_id,
        'workspace_name', p_workspace_name,
        'created_at',     v_now,
        'updated_at',     v_now
    );
END;
$$;
