-- upgrade
-- Evaluate workspace authorisation once per statement instead of once
-- per row.
--
-- V33's policies call check_workspace_permission(workspace_id, user,
-- action) with workspace_id taken from the candidate row, so the call
-- is correlated and runs for every row the policy filters. It cannot be
-- optimised away either: the function is SECURITY DEFINER, and
-- PostgreSQL does not inline SECURITY DEFINER SQL functions, so this is
-- a genuine function invocation per row rather than an EXISTS folded
-- into the plan.
--
-- The fix is to collect the caller's authorised workspace set once and
-- test membership per row. The set-returning function takes only the
-- action, so the subquery is uncorrelated and PostgreSQL evaluates it a
-- single time (hashed SubPlan) for the whole statement.
--
-- A plain subquery on workspace_members inside a policy does NOT work,
-- which is why V33 reached for a function in the first place: that
-- subquery would itself be filtered by workspace_members' own
-- owner-only policy, so a non-owner member would read an empty set and
-- lose access to their own data. The set function stays SECURITY
-- DEFINER for exactly the reason V33 documented -- its own read of
-- workspace_members must not re-enter the policy that calls it.
--
-- Semantics are unchanged. 'read' gates SELECT; 'write' gates
-- INSERT/UPDATE/DELETE on tables/rows/table_views; 'owner' gates
-- workspace mutation and every command on workspace_members. With no
-- app.current_user_id set, current_setting(...,TRUE) is NULL, the
-- comparison never matches, the set is empty, and `IN (empty)` is
-- FALSE -- the same closed door V33 produced by returning false.
--
-- Why not make the predicate inlinable instead? Because it cannot be
-- here. PostgreSQL refuses to inline a SECURITY DEFINER function
-- (inline_function() and inline_set_returning_function() both reject on
-- prosecdef), so this predicate stays opaque to the planner. Replacing
-- it with a plain subquery on workspace_members would be inlinable, but
-- that subquery is itself filtered by workspace_members' own policies,
-- and the owner policy must read workspace_members to answer "am I an
-- owner" -- which is only non-recursive via SECURITY DEFINER. The
-- function call would therefore not disappear, only move from once per
-- rows row to once per membership row.
--
-- What actually matters is that the predicate is *uncorrelated*: it
-- takes only the action, never the candidate row, so it is evaluated
-- once per statement rather than once per row. The residual cost is
-- that the planner cannot see into the set, which the ROWS estimate
-- below addresses -- a set-returning function otherwise defaults to an
-- estimate of 1000 rows, and no user is a member of 1000 workspaces.
--
-- check_workspace_permission is deliberately NOT dropped: V47's index
-- helpers and V49's create_row_data_index still need a scalar,
-- single-workspace check, and both are SECURITY DEFINER functions doing
-- DDL that RLS cannot govern. Its eight call sites in
-- backend/src/repository/workspace.py are a separate problem -- see the
-- note at the end of this file.
--
-- This is 17 security policies. It must not be applied before
-- migration/test_migration_rls.py passes.

-- ── Authorised workspace set for the current session ────────────────────

CREATE OR REPLACE FUNCTION public.current_user_workspaces(
    p_action VARCHAR
) RETURNS SETOF UUID
LANGUAGE sql
SECURITY DEFINER
STABLE
PARALLEL SAFE
ROWS 16
SET search_path = public, pg_temp
AS $$
    SELECT member.workspace_id
    FROM   public.workspace_members AS member
    WHERE  member.user_id = (
               nullif(current_setting('app.current_user_id', TRUE), '')
           )::UUID
    AND    member.action = p_action;
$$;

REVOKE ALL    ON
    FUNCTION public.current_user_workspaces(VARCHAR) FROM public;
GRANT EXECUTE ON
    FUNCTION public.current_user_workspaces(VARCHAR) TO app, mgr;

-- ── workspace_members — owner only, every command ───────────────────────
-- FOR ALL with USING only, as in V33: PostgreSQL reuses USING as the
-- INSERT/UPDATE check when WITH CHECK is omitted.

DROP POLICY IF EXISTS workspace_members_owner ON public.workspace_members;
CREATE POLICY workspace_members_owner ON public.workspace_members
USING (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('owner') AS allowed(workspace_id)
    )
);

-- ── workspace_members — a member may read their own grants ──────────────
-- V33 made this table owner-only for every command, which is why
-- repository/workspace.py had to route five questions through
-- check_workspace_permission: under an owner-only SELECT policy a
-- non-owner querying their *own* membership reads nothing, because the
-- policy asks "is the caller an owner here", never "is this the
-- caller's own row". Both docstrings in that file say so explicitly.
--
-- Without this policy there is no RLS-legal replacement for
-- get_first_owned_workspace: the workspaces SELECT policy expresses
-- 'read' and cannot express "workspaces I own".
--
-- It discloses nothing new. The rows are the caller's own
-- (workspace_id, user_id, action), and the caller already receives
-- their level for every workspace in the sidebar payload
-- (SidebarPayload.workspaces[].level, computed today by
-- get_user_level). Seeing *other* members remains owner-only: this
-- policy is SELECT-only and self-scoped, and permissive policies OR
-- together, so an owner keeps the full roster while a member sees one
-- row per grant they hold.

DROP POLICY IF EXISTS workspace_members_self_read ON public.workspace_members;
CREATE POLICY workspace_members_self_read ON public.workspace_members
FOR SELECT
USING (
    user_id = (
        nullif(current_setting('app.current_user_id', TRUE), '')
    )::UUID
);

-- ── workspaces — read to view, owner to mutate ──────────────────────────

DROP POLICY IF EXISTS workspaces_read ON public.workspaces;
CREATE POLICY workspaces_read ON public.workspaces
FOR SELECT
USING (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('read') AS allowed(workspace_id)
    )
);

DROP POLICY IF EXISTS workspaces_owner_insert ON public.workspaces;
CREATE POLICY workspaces_owner_insert ON public.workspaces
FOR INSERT
WITH CHECK (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('owner') AS allowed(workspace_id)
    )
);

DROP POLICY IF EXISTS workspaces_owner_update ON public.workspaces;
CREATE POLICY workspaces_owner_update ON public.workspaces
FOR UPDATE
USING (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('owner') AS allowed(workspace_id)
    )
)
WITH CHECK (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('owner') AS allowed(workspace_id)
    )
);

DROP POLICY IF EXISTS workspaces_owner_delete ON public.workspaces;
CREATE POLICY workspaces_owner_delete ON public.workspaces
FOR DELETE
USING (
    workspace_id IN (
        SELECT allowed.workspace_id
        FROM public.current_user_workspaces('owner') AS allowed(workspace_id)
    )
);

-- ── tables / rows / table_views — read to view, write to mutate ─────────

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['tables', 'rows', 'table_views'] LOOP
        EXECUTE format(
            'DROP POLICY IF EXISTS %I_read ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_read ON public.%I
             FOR SELECT
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''read'') AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_insert ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_insert ON public.%I
             FOR INSERT
             WITH CHECK (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'') AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_update ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_update ON public.%I
             FOR UPDATE
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'') AS allowed(workspace_id)
                 )
             )
             WITH CHECK (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'') AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_delete ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_delete ON public.%I
             FOR DELETE
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'') AS allowed(workspace_id)
                 )
             )', t, t
        );
    END LOOP;
END $$;

-- ── Follow-up, deliberately NOT done here ───────────────────────────────
-- Authorisation belongs in RLS, so the backend should not be asking
-- permission questions of its own. Eight call sites in
-- backend/src/repository/workspace.py still do:
--   * list_by_user / owner listing put
--     check_workspace_permission(workspaces.workspace_id, ...) in a
--     WHERE clause -- the same per-row opaque call this migration just
--     removed from the policies, reintroduced in application SQL. With
--     RLS in place the predicate is redundant: a bare
--     SELECT ... FROM workspaces already returns exactly the readable
--     rows.
--   * is_member / is_owner / can_write and the level CASE issue three
--     more scalar calls to pre-check what the subsequent statement's
--     policy would enforce anyway.
--
-- The self-read policy above is what makes removing them possible;
-- V53 then revokes app's EXECUTE so the deviation cannot return.
--
-- No phased rollout: this release is breaking and ships behind an
-- announced maintenance window, migrations first. There is no moment at
-- which old code has to run against the new schema, so the revoke does
-- not have to wait for a follow-up deploy.
