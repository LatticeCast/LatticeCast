-- upgrade
-- Row-data HTTP semantics live in PostgreSQL. All mutations are SECURITY
-- INVOKER so the rows RLS policies protect them automatically.

CREATE OR REPLACE FUNCTION public._validate_row_data_mutation(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_data         JSONB
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
BEGIN
    IF jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'row data must be a JSON object'
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
        INNER JOIN jsonb_object_keys(p_data) AS data_column_id
            ON data_column_id = column_data ->> 'column_id'
        WHERE column_data ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob column values must use update_blob_cell'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_columns;
END;
$$;

CREATE OR REPLACE FUNCTION public.patch_row_data(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_patch        JSONB
) RETURNS PUBLIC.ROWS
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_by  UUID;
    v_row public.rows;
BEGIN
    PERFORM public._validate_row_data_mutation(p_workspace_id, p_table_id, p_patch);
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

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

CREATE OR REPLACE FUNCTION public.put_row_data(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_data         JSONB
) RETURNS PUBLIC.ROWS
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_by         UUID;
    v_columns    JSONB;
    v_current    public.rows;
    v_blob_cells JSONB;
    v_row        public.rows;
BEGIN
    v_columns := public._validate_row_data_mutation(
        p_workspace_id, p_table_id, p_data
    );
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    SELECT *
    INTO   v_current
    FROM   public.rows
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    row_id       = p_row_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'row not found: %, %, %',
            p_workspace_id, p_table_id, p_row_id;
    END IF;

    SELECT coalesce(
        jsonb_object_agg(
            column_data ->> 'column_id',
            v_current.row_data -> (column_data ->> 'column_id')
        ),
        '{}'::JSONB
    )
    INTO v_blob_cells
    FROM jsonb_array_elements(v_columns) AS column_data
    WHERE column_data ->> 'type' = 'blob'
    AND   v_current.row_data ? (column_data ->> 'column_id');

    UPDATE public.rows
    SET    row_data   = v_blob_cells || p_data,
           updated_by = v_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    row_id       = p_row_id
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

-- V44 created this function as SECURITY DEFINER. Recreate it under the
-- caller's app role so its SELECT/UPDATE are governed by rows RLS.
CREATE OR REPLACE FUNCTION public.update_blob_cell(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_column_id    TEXT,
    p_metadata     JSONB
) RETURNS PUBLIC.ROWS
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_by      UUID;
    v_columns JSONB;
    v_row     public.rows;
BEGIN
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

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

DROP FUNCTION IF EXISTS public.update_row_data(UUID, VARCHAR, BIGINT, JSONB);

REVOKE ALL ON
    FUNCTION public._validate_row_data_mutation(UUID, VARCHAR, JSONB) FROM public;
REVOKE ALL ON
    FUNCTION public.patch_row_data(UUID, VARCHAR, BIGINT, JSONB) FROM public;
REVOKE ALL ON
    FUNCTION public.put_row_data(UUID, VARCHAR, BIGINT, JSONB) FROM public;
GRANT EXECUTE ON
    FUNCTION public._validate_row_data_mutation(UUID, VARCHAR, JSONB) TO app;
GRANT EXECUTE ON
    FUNCTION public.patch_row_data(UUID, VARCHAR, BIGINT, JSONB) TO app;
GRANT EXECUTE ON
    FUNCTION public.put_row_data(UUID, VARCHAR, BIGINT, JSONB) TO app;
