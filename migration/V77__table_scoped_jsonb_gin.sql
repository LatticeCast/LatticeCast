-- A single physical rows table holds every tenant's dynamic columns.
-- Select, tags and checkbox containment uses one shared multicolumn GIN.
-- Numeric and date range queries retain their per-column B-tree indexes.
-- The manual ops/rebuild_rows_gin.py workflow installs btree_gin, builds the
-- new GIN concurrently, then retires superseded indexes after verification.

-- Retain validation. add_column() still calls this helper for text/string/url
-- until its own contract is replaced; those types now create no index.
-- The old shared row_data GIN remains until the manual replacement is ready.
CREATE OR REPLACE FUNCTION public._create_row_data_index_unchecked(
    p_workspace_id UUID,
    p_idx_name    TEXT,
    p_table_id    BIGINT,
    p_column_id   TEXT,
    p_col_type    TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_idx_name <> public._build_rd_idx_name(
        p_workspace_id, p_table_id, p_column_id
    ) THEN
        RAISE EXCEPTION 'invalid row-data index name'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_col_type NOT IN (
        'number', 'date', 'datetime', 'text', 'string', 'select',
        'tags', 'url', 'checkbox'
    ) THEN
        RAISE EXCEPTION 'unsupported indexed column type: %', p_col_type
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.tables AS table_data
        CROSS JOIN LATERAL jsonb_array_elements(
            table_data.config -> 'columns'
        ) AS column_data
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
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    ELSIF p_col_type IN ('date', 'datetime') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_column_id, p_table_id
        );
    ELSIF p_col_type IN ('text', 'string', 'url') THEN
        RETURN;
    ELSIF EXISTS (
        SELECT 1 FROM pg_index AS ix
        WHERE ix.indexrelid IN (
            to_regclass('public.idx_rows_row_data_gin'),
            to_regclass('public.idx_rows_table_data_gin')
        ) AND ix.indrelid = 'public.rows'::regclass
          AND ix.indisvalid AND ix.indisready
    ) THEN
        RETURN;
    ELSE
        RAISE EXCEPTION 'shared rows GIN index is missing or invalid'
            USING ERRCODE = 'object_not_in_prerequisite_state';
    END IF;
END;
$function$;
