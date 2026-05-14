-- upgrade
-- Row-Level Security. mgr is BYPASSRLS (see V1) so admin paths are
-- unaffected. app must set the session var `app.current_user_id` to the
-- authenticated user's UUID per request; policies filter rows by that.
--
-- Two policy shapes:
--   gdpr.user_info   — self only (user_id matches current user)
--   public.*         — workspace member only (via check_workspace_member)

-- ── Helpers ─────────────────────────────────────────────────────────────────
-- SECURITY DEFINER on check_workspace_member is required: the function
-- queries public.workspace_members, which itself has an RLS policy that
-- calls check_workspace_member. Without SECURITY DEFINER the policy
-- would recurse infinitely. STABLE lets PG cache the result within a
-- single statement.

CREATE OR REPLACE FUNCTION public.check_workspace_member(
    ws_id UUID,
    u_id  UUID
) RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM   public.workspace_members
        WHERE  workspace_id = ws_id
        AND    user_id      = u_id
    );
$$;

REVOKE ALL    ON FUNCTION public.check_workspace_member(UUID, UUID) FROM public;
GRANT EXECUTE ON FUNCTION public.check_workspace_member(UUID, UUID) TO app, mgr;

-- ── gdpr.user_info: self only ───────────────────────────────────────────────

ALTER TABLE gdpr.user_info ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_info_self ON gdpr.user_info;
CREATE POLICY user_info_self ON gdpr.user_info
USING (
    user_id = (nullif(current_setting('app.current_user_id', true), ''))::UUID
);

-- ── public tables: workspace member only ────────────────────────────────────

ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspaces_workspace_member ON public.workspaces;
CREATE POLICY workspaces_workspace_member ON public.workspaces
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);

ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_members_workspace_member ON public.workspace_members;
CREATE POLICY workspace_members_workspace_member ON public.workspace_members
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);

ALTER TABLE public.tables ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tables_workspace_member ON public.tables;
CREATE POLICY tables_workspace_member ON public.tables
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);

ALTER TABLE public.rows ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rows_workspace_member ON public.rows;
CREATE POLICY rows_workspace_member ON public.rows
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);

ALTER TABLE public.table_schemas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS table_schemas_workspace_member ON public.table_schemas;
CREATE POLICY table_schemas_workspace_member ON public.table_schemas
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);

ALTER TABLE public.table_views ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS table_views_workspace_member ON public.table_views;
CREATE POLICY table_views_workspace_member ON public.table_views
USING (
    public.check_workspace_member(
        workspace_id,
        (nullif(current_setting('app.current_user_id', true), ''))::UUID
    )
);
