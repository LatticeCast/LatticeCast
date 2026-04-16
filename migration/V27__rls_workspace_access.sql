-- upgrade
-- 0027_rls_workspace_access.sql
-- task-244: Enable RLS on rows and tables — workspace membership enforced at
-- DB
--
-- Scope: rows + tables only.
-- workspaces / workspace_members are excluded to avoid bootstrap deadlock
-- (a new workspace has no members yet, so RLS FOR ALL would block its own
-- INSERT).
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

-- get_table_workspace_id: look up a table's workspace without triggering
-- tables RLS (called from within the rows policy to avoid nested policy
-- evaluation on tables)
CREATE OR REPLACE FUNCTION get_table_workspace_id(t_id text)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT workspace_id FROM public.tables WHERE table_id = t_id;
$$;

-- ── DDL helpers for per-column row_data indexes ──────────────────────────────
-- app_user has no DDL privileges, but per-column JSONB indexes must be
-- created/dropped at request time. These SECURITY DEFINER functions run as
-- dba (the function owner) so the caller doesn't need CREATE/OWN privileges.
--
-- Inputs are composed into identifiers, so callers MUST pass sanitized
-- values (UUID hex fragments, known column types). The repository layer
-- builds these from validated types/UUIDs.

CREATE OR REPLACE FUNCTION create_row_data_index(
    p_idx_name text,
    p_table_id text,
    p_column_id text,
    p_col_type text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    expr text;
    sql text;
BEGIN
    -- Reject names that don't match our generated format
    IF p_idx_name !~ '^idx_rd_[a-zA-Z0-9_]+$' THEN
        RAISE EXCEPTION 'invalid index name: %', p_idx_name;
    END IF;
    IF p_column_id !~ '^[a-zA-Z0-9_-]+$' THEN
        RAISE EXCEPTION 'invalid column_id: %', p_column_id;
    END IF;

    IF p_col_type = 'number' THEN
        expr := format(
            '((row_data->>%L)::numeric)', p_column_id
        );
        sql := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows (%s) '
            'WHERE table_id = %L',
            p_idx_name, expr, p_table_id
        );
    ELSIF p_col_type = 'date' THEN
        expr := format('((row_data->>%L))', p_column_id);
        sql := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows (%s) '
            'WHERE table_id = %L',
            p_idx_name, expr, p_table_id
        );
    ELSIF p_col_type IN ('select', 'tags', 'text', 'checkbox') THEN
        sql := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING GIN ((row_data->%L)) WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    ELSE
        -- Unsupported type: no-op
        RETURN;
    END IF;

    EXECUTE sql;
END;
$$;

CREATE OR REPLACE FUNCTION drop_row_data_index(p_idx_name text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_idx_name !~ '^idx_rd_[a-zA-Z0-9_]+$' THEN
        RAISE EXCEPTION 'invalid index name: %', p_idx_name;
    END IF;
    EXECUTE format('DROP INDEX IF EXISTS public.%I', p_idx_name);
END;
$$;

GRANT EXECUTE ON FUNCTION create_row_data_index(text, text, text, text) TO app;
GRANT EXECUTE ON FUNCTION drop_row_data_index(text) TO app;

-- ── Enable RLS ──────────────────────────────────────────────────────────────

ALTER TABLE public.tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rows ENABLE ROW LEVEL SECURITY;

-- ── Policies ────────────────────────────────────────────────────────────────

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
