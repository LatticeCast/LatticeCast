-- V40 — reject duplicate normalized column names before mutation writes.
--
-- V39's trigger remains the final guard for all direct writes to
-- public.tables.config. These function-level checks make the normal column
-- mutation path return the same clear error before attempting its update.

CREATE OR REPLACE FUNCTION public.add_column(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_name         TEXT,
    p_type         TEXT,
    p_options      JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns   JSONB;
    v_new_col   JSONB;
    v_col_id    TEXT;
    v_new_cfg   JSONB;
    v_idx_name  TEXT;
BEGIN
    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    v_new_col := _build_column_dict(p_name, p_type, p_options);
    v_col_id  := v_new_col ->> 'column_id';

    IF NOT public._column_names_are_unique(v_columns || v_new_col) THEN
        RAISE EXCEPTION 'duplicate normalized column name'
            USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE public.tables
    SET    config = jsonb_set(
               config,
               '{columns}',
               COALESCE(config -> 'columns', '[]'::JSONB)
                   || v_new_col
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF p_type IN (
        'number', 'date', 'datetime',
        'text', 'string', 'select', 'tags',
        'email', 'url', 'phone', 'checkbox'
    ) THEN
        v_idx_name := _build_rd_idx_name(
            p_table_id::TEXT, v_col_id
        );
        PERFORM create_row_data_index(
            v_idx_name, p_table_id::TEXT, v_col_id, p_type
        );
    END IF;

    RETURN v_new_cfg;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_column(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_column_id    TEXT,
    p_patch        JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_old_columns JSONB;
    v_new_columns JSONB;
    v_found       BOOLEAN := FALSE;
    v_new_cfg     JSONB;
BEGIN
    SELECT config -> 'columns'
    INTO   v_old_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_old_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    SELECT jsonb_agg(
        CASE
            WHEN c ->> 'column_id' = p_column_id
                THEN c || p_patch
            ELSE c
        END
    ),
    bool_or(c ->> 'column_id' = p_column_id)
    INTO v_new_columns, v_found
    FROM jsonb_array_elements(v_old_columns) AS c;

    IF NOT v_found THEN
        RAISE EXCEPTION 'column not found: %', p_column_id;
    END IF;

    IF NOT public._column_names_are_unique(v_new_columns) THEN
        RAISE EXCEPTION 'duplicate normalized column name'
            USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE public.tables
    SET    config     = jsonb_set(
               config, '{columns}', v_new_columns
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;
