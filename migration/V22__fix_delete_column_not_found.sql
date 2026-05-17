-- V22: fix delete_column — bool_or on filtered set always returns NULL
--
-- Bug: the WHERE clause removes the target column BEFORE bool_or checks
-- for it, so v_found is always NULL → "column not found" on every call.
-- Fix: check existence separately, then filter.

CREATE OR REPLACE FUNCTION public.delete_column(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_column_id    TEXT,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_old_columns JSONB;
    v_new_columns JSONB;
    v_new_cfg     JSONB;
    v_idx_name    TEXT;
BEGIN
    SELECT config -> 'columns'
    INTO   v_old_columns
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_old_columns IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    -- Check column exists before filtering
    IF NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(v_old_columns) AS c
        WHERE c ->> 'column_id' = p_column_id
    ) THEN
        RAISE EXCEPTION 'column not found: %', p_column_id;
    END IF;

    -- Remove the column
    SELECT COALESCE(jsonb_agg(c), '[]'::JSONB)
    INTO   v_new_columns
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' <> p_column_id;

    UPDATE public.table_schemas
    SET    config     = jsonb_set(config, '{columns}', v_new_columns),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    -- Drop the filter index if present.
    v_idx_name := _build_rd_idx_name(p_table_id::TEXT, p_column_id);
    PERFORM drop_row_data_index(v_idx_name);

    RETURN v_new_cfg;
END;
$$;
