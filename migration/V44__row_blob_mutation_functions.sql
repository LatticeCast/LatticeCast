-- upgrade
-- Row mutations cross a blob boundary: ordinary updates may merge only
-- non-blob cells, while storage-backed blob metadata is updated by one
-- explicitly addressed function.  Both functions use the request's RLS
-- user context because SECURITY DEFINER otherwise bypasses row policies.

CREATE OR REPLACE FUNCTION public.update_row_data(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_patch        JSONB
) RETURNS PUBLIC.ROWS
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_by           UUID;
    v_columns      JSONB;
    v_row          public.rows;
BEGIN
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    IF v_by IS NULL OR NOT public.check_workspace_permission(
        p_workspace_id, v_by, 'write'
    ) THEN
        RAISE EXCEPTION 'write permission required for workspace %', p_workspace_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF jsonb_typeof(p_patch) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'row patch must be a JSON object'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(v_columns) AS column_data
        INNER JOIN jsonb_object_keys(p_patch) AS patch_column_id
            ON patch_column_id = column_data ->> 'column_id'
        WHERE column_data ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob column values must use update_blob_cell'
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.rows
    SET    row_data   = row_data || p_patch,
           updated_by = v_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    row_id       = p_row_id
    RETURNING * INTO v_row;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'row not found: %, %, %',
            p_workspace_id, p_table_id, p_row_id;
    END IF;

    RETURN v_row;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_blob_cell(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_column_id    TEXT,
    p_metadata     JSONB
) RETURNS PUBLIC.ROWS
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_by           UUID;
    v_columns      JSONB;
    v_row          public.rows;
BEGIN
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    IF v_by IS NULL OR NOT public.check_workspace_permission(
        p_workspace_id, v_by, 'write'
    ) THEN
        RAISE EXCEPTION 'write permission required for workspace %', p_workspace_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF jsonb_typeof(p_metadata) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'blob metadata must be a JSON object'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(v_columns) AS column_data
        WHERE column_data ->> 'column_id' = p_column_id
        AND   column_data ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob column not found: %', p_column_id
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.rows
    SET    row_data   = jsonb_set(row_data, ARRAY[p_column_id], p_metadata, TRUE),
           updated_by = v_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    row_id       = p_row_id
    RETURNING * INTO v_row;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'row not found: %, %, %',
            p_workspace_id, p_table_id, p_row_id;
    END IF;

    RETURN v_row;
END;
$$;

REVOKE ALL ON
    FUNCTION public.update_row_data(UUID, VARCHAR, BIGINT, JSONB) FROM public;
REVOKE ALL ON
    FUNCTION public.update_blob_cell(UUID, VARCHAR, BIGINT, TEXT, JSONB) FROM public;
GRANT EXECUTE ON
    FUNCTION public.update_row_data(UUID, VARCHAR, BIGINT, JSONB) TO app;
GRANT EXECUTE ON
    FUNCTION public.update_blob_cell(UUID, VARCHAR, BIGINT, TEXT, JSONB) TO app;
