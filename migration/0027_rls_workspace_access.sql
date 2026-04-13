-- 0027_rls_workspace_access.sql
-- task-244: Enable RLS on rows and tables — workspace membership enforced at DB
--
-- Scope: rows + tables only.
-- workspaces / workspace_members are excluded to avoid bootstrap deadlock
-- (a new workspace has no members yet, so RLS FOR ALL would block its own INSERT).
-- Application code enforces access control on those tables.

-- ── Helper functions (SECURITY DEFINER — run as dba which has BYPASSRLS) ─────

-- check_workspace_member: used in policies to avoid self-referential recursion
-- on workspace_members if that table ever gets RLS in the future.
CREATE OR REPLACE FUNCTION check_workspace_member(ws_id uuid, u_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = ws_id AND user_id = u_id
  );
$$;

-- get_table_workspace_id: look up a table's workspace without triggering tables RLS
-- (called from within the rows policy to avoid nested policy evaluation on tables)
CREATE OR REPLACE FUNCTION get_table_workspace_id(t_id text)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT workspace_id FROM public.tables WHERE table_id = t_id;
$$;

-- ── Enable RLS ────────────────────────────────────────────────────────────────

ALTER TABLE public.tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rows   ENABLE ROW LEVEL SECURITY;

-- ── Policies ──────────────────────────────────────────────────────────────────

-- tables: user must be a member of the workspace
CREATE POLICY tables_workspace_member ON public.tables
  FOR ALL
  USING (
    check_workspace_member(
      workspace_id,
      current_setting('app.current_user_id', true)::uuid
    )
  );

-- rows: user must be a member of the workspace that owns the table
-- get_table_workspace_id bypasses tables RLS to avoid nested policy loops
CREATE POLICY rows_workspace_member ON public.rows
  FOR ALL
  USING (
    check_workspace_member(
      get_table_workspace_id(table_id),
      current_setting('app.current_user_id', true)::uuid
    )
  );

-- ── DBA bypasses RLS (migrations, admin tasks) ────────────────────────────────

DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'dba') THEN
    ALTER ROLE dba BYPASSRLS;
  END IF;
END $$;
