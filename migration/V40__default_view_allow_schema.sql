-- upgrade
-- V40: Extend set_table_default_view to accept the implicit Schema tab.
--
-- V37's set_table_default_view rejected type='schema' so the implicit
-- "Schema" tab in the FE couldn't be flagged as the table's default. But
-- the FE renders __schema__ as a user-clickable tab labeled "Schema",
-- and users expect clicking it to make it the resume target.
--
-- Solution: translate "Schema" (FE display name) → "__schema__" (DB row
-- name) inside the function, and remove the 'schema' rejection. Order
-- rows ('__order__') stay rejected — they're never a valid view.
--
-- Mirror translation: get_default_view_name (Python repo) needs to
-- return 'Schema' to the FE when __schema__.is_default is true. That
-- lives in repository/table_view.py.

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
    v_target_name VARCHAR;
    v_type VARCHAR;
BEGIN
    -- "Schema" is the FE display name for the __schema__ row.
    IF p_view_name IN ('Schema', '__schema__') THEN
        v_target_name := '__schema__';
    ELSE
        v_target_name := p_view_name;
    END IF;

    SELECT type INTO v_type
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = v_target_name;

    IF v_type IS NULL THEN
        RAISE EXCEPTION
            'View "%" not found for table % (workspace=%)',
            p_view_name, p_table_id, p_workspace_id;
    END IF;
    -- The __order__ row is never a valid default view; only 'schema' or
    -- one of the user view types may carry is_default=true.
    IF v_type = 'order' THEN
        RAISE EXCEPTION
            'Cannot mark internal "order" view as default';
    END IF;

    UPDATE public.table_views
    SET is_default = false
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND is_default;

    UPDATE public.table_views
    SET is_default = true
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = v_target_name;
END;
$$;
