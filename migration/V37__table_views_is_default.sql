-- upgrade
-- V37: Per-table "default view" pointer, stored as a flag on table_views.
--
-- Goals:
--   - Clicking a view marks it as the table's default so the next visit
--     (without ?view= URL param) resumes there.
--   - Avoid a circular FK between public.tables and public.table_views.
--   - "Exactly one default per table" enforced by a partial unique index.
--
-- The actual flip is performed via a SECURITY DEFINER helper function so
-- the app role gets a single atomic call instead of doing two UPDATEs.

ALTER TABLE public.table_views
ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false;

-- One default per (workspace_id, table_id) — partial unique index.
CREATE UNIQUE INDEX IF NOT EXISTS table_views_one_default
ON public.table_views (workspace_id, table_id)
WHERE is_default;

-- Atomic flip helper: clears the existing default (if any) and marks the
-- named view as default. Validates the target view exists and is a
-- user-visible view (table/kanban/timeline/dashboard) — refuses to mark
-- the __schema__ or __order__ rows as default.
CREATE OR REPLACE FUNCTION SET_TABLE_DEFAULT_VIEW(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_view_name VARCHAR
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_type VARCHAR;
BEGIN
    SELECT type INTO v_type
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = p_view_name;

    IF v_type IS NULL THEN
        RAISE EXCEPTION
            'View "%" not found for table % (workspace=%)',
            p_view_name, p_table_id, p_workspace_id;
    END IF;
    IF v_type IN ('schema', 'order') THEN
        RAISE EXCEPTION
            'Cannot mark internal "%" view as default',
            v_type;
    END IF;

    -- Clear current default (no-op if none).
    UPDATE public.table_views
    SET is_default = false
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND is_default;

    -- Mark the target.
    UPDATE public.table_views
    SET is_default = true
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = p_view_name;
END;
$$;

GRANT EXECUTE ON FUNCTION
SET_TABLE_DEFAULT_VIEW(UUID, VARCHAR, VARCHAR)
TO app;
