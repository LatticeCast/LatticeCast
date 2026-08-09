-- V34 — deduplicate sidebar payload after action-grant migration
--
-- V33 changed workspace_members from one row per member to one row per
-- granted action.  Joining it directly multiplied every workspace and table
-- in get_user_sidebar() by the number of actions held by the user.
--
-- Membership is an existence check here, so use EXISTS and keep each
-- workspace/table sourced from its own primary-keyed table exactly once.

CREATE OR REPLACE FUNCTION public.get_user_sidebar(p_user_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT jsonb_build_object(
        'workspaces', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id',   w.workspace_id,
                    'workspace_name', w.workspace_name
                )
                ORDER BY w.workspace_name
            )
            FROM public.workspaces w
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members m
                WHERE m.workspace_id = w.workspace_id
                  AND m.user_id = p_user_id
            )
        ), '[]'::JSONB),
        'tables', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id', t.workspace_id,
                    'table_id',     t.table_id,
                    'config',       t.config
                )
                ORDER BY t.workspace_id, t.table_id
            )
            FROM public.tables t
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members m
                WHERE m.workspace_id = t.workspace_id
                  AND m.user_id = p_user_id
            )
        ), '[]'::JSONB)
    );
$$;

REVOKE ALL ON FUNCTION public.get_user_sidebar(UUID) FROM public;
GRANT EXECUTE ON FUNCTION public.get_user_sidebar(UUID) TO app, mgr;
