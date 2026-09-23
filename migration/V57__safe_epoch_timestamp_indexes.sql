-- upgrade
-- Make date/datetime expression indexes tolerant of any legacy non-numeric
-- row_data cells. V49 has already been applied and must remain immutable.

CREATE OR REPLACE FUNCTION public.create_row_data_index(
    p_workspace_id UUID,
    p_idx_name     TEXT,
    p_table_id     TEXT,
    p_column_id    TEXT,
    p_col_type     TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL
        OR NOT public.check_workspace_permission(p_workspace_id, v_user_id, 'write')
    THEN
        RAISE EXCEPTION 'write permission required for workspace %', p_workspace_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_idx_name <> public._build_rd_idx_name(
        p_workspace_id, p_table_id, p_column_id
    ) THEN
        RAISE EXCEPTION 'invalid row-data index name'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_col_type NOT IN (
        'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
        'email', 'url', 'phone', 'checkbox'
    ) THEN
        RAISE EXCEPTION 'unsupported indexed column type: %', p_col_type
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.tables AS table_data
        CROSS JOIN LATERAL jsonb_array_elements(table_data.config -> 'columns') AS column_data
        WHERE table_data.workspace_id = p_workspace_id
          AND table_data.table_id = p_table_id
          AND column_data ->> 'column_id' = p_column_id
          AND column_data ->> 'type' = p_col_type
    ) THEN
        RAISE EXCEPTION 'indexed column not found: %', p_column_id
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_col_type = 'number' THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree (((row_data ->> %L)::NUMERIC)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_workspace_id, p_table_id
        );
    ELSIF p_col_type IN ('date', 'datetime') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_column_id, p_workspace_id, p_table_id
        );
    ELSIF p_col_type IN ('text', 'string', 'select', 'email', 'url', 'phone') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((row_data ->> %L)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_workspace_id, p_table_id
        );
    ELSE
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING gin ((row_data -> %L)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_workspace_id, p_table_id
        );
    END IF;
END;
$$;

-- Replace V49's unguarded date/datetime indexes with a safe expression.
DO $$
DECLARE
    r          RECORD;
    v_idx_name TEXT;
BEGIN
    FOR r IN
        SELECT table_data.workspace_id,
               table_data.table_id,
               column_data ->> 'column_id' AS column_id
        FROM public.tables AS table_data
        CROSS JOIN LATERAL jsonb_array_elements(table_data.config -> 'columns') AS column_data
        WHERE column_data ->> 'type' IN ('date', 'datetime')
    LOOP
        v_idx_name := public._build_rd_idx_name(
            r.workspace_id, r.table_id, r.column_id
        );
        EXECUTE format('DROP INDEX IF EXISTS public.%I', v_idx_name);
        EXECUTE format(
            'CREATE INDEX %I ON public.rows '
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            v_idx_name, r.column_id, r.column_id, r.workspace_id, r.table_id
        );
    END LOOP;
END;
$$;
