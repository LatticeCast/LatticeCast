-- The home preload is get_workspaces_tables(), matching its endpoint
-- GET /api/v1/workspaces_tables. get_user_sidebar() was the old name and is
-- dropped.
--
-- Each workspace now carries created_at, in a stable order: names are not
-- unique, and the client addresses a duplicate by name plus a creation-order
-- suffix (name, name-1, name-2).
CREATE OR REPLACE FUNCTION public.get_workspaces_tables()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN jsonb_build_object(
        'workspaces', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id',   workspace.workspace_id,
                    'workspace_name', workspace.workspace_name,
                    'created_at',     workspace.created_at
                )
                ORDER BY workspace.workspace_name, workspace.created_at, workspace.workspace_id
            )
            FROM public.workspaces AS workspace
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = workspace.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB),
        'tables', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id', table_data.workspace_id,
                    'table_id',     table_data.table_id,
                    'table_name',   table_data.table_name,
                    'config',       table_data.config
                )
                ORDER BY table_data.workspace_id, table_data.table_name
            )
            FROM public.tables AS table_data
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = table_data.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB)
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.get_workspaces_tables() FROM public;
GRANT EXECUTE ON FUNCTION public.get_workspaces_tables() TO app, mgr;

DROP FUNCTION IF EXISTS public.get_user_sidebar();
