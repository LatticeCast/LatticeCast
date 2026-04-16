-- upgrade
-- V30: Fix RLS policies — handle empty/missing app.current_user_id without
-- crashing.
-- Previously: current_setting('app.current_user_id', true)::uuid → fails on ""
-- Now: NULLIF guards empty string, returns NULL → policy denies cleanly

DROP POLICY IF EXISTS tables_workspace_member ON public.tables;
CREATE POLICY tables_workspace_member ON public.tables
FOR ALL
USING (
    check_workspace_member(
        workspace_id,
        nullif(current_setting('app.current_user_id', true), '')::uuid
    )
);

DROP POLICY IF EXISTS rows_workspace_member ON public.rows;
CREATE POLICY rows_workspace_member ON public.rows
FOR ALL
USING (
    check_workspace_member(
        workspace_id,
        nullif(current_setting('app.current_user_id', true), '')::uuid
    )
);
