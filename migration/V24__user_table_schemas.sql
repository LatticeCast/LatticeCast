-- V24 — get_user_sidebar(user_id)
--
-- Returns sidebar/home preload payload in one round trip:
--   { "workspaces": [{workspace_id, workspace_name}, ...],
--     "tables":     [{workspace_id, table_id, config},   ...] }
--
-- Two separate arrays, NOT joined — so empty workspaces still appear
-- (their workspace_id simply has no entry in the tables array). This
-- eliminates the first-table-click latency spike on the FE: every
-- schema is already in memory; only rows still round-trip.
--
-- SECURITY DEFINER: skips RLS so a single query can scan every workspace
-- the user is a member of. The WHERE m.user_id = p_user_id is the
-- security check — only rows the caller owns via workspace_members are
-- ever materialised.

DROP FUNCTION IF EXISTS public.get_user_table_schemas(UUID);

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
            FROM public.workspace_members m
            JOIN public.workspaces        w USING (workspace_id)
            WHERE m.user_id = p_user_id
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
            FROM public.workspace_members m
            JOIN public.tables            t USING (workspace_id)
            WHERE m.user_id = p_user_id
        ), '[]'::JSONB)
    );
$$;

REVOKE ALL    ON
    FUNCTION public.get_user_sidebar(UUID) FROM public;
GRANT EXECUTE ON
    FUNCTION public.get_user_sidebar(UUID) TO app, mgr;
