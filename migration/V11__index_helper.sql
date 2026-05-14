-- upgrade
-- Per-column index helpers for public.rows. row_data is a JSONB keyed
-- by column_id; we keep one partial index per (table_id, column_id) so
-- query planners can use it for column-filter searches. The index type
-- (btree-numeric / btree-text / GIN) is chosen by the column's logical
-- type.
--
-- SECURITY DEFINER: callers (mgr/app) have no DDL, but adding a column
-- needs CREATE INDEX. The function runs as its owner (dba_user) which
-- has CREATE on public schema.

-- ── Standard index name for (table_id, column_id) ──────────────────────────
-- Format: idx_rd_<sanitized_table_id>_<first 12 hex chars of column_id>.
-- Fits PG's 63-char limit even for long table_ids.

CREATE OR REPLACE FUNCTION public._build_rd_idx_name(
    p_table_id  TEXT,
    p_column_id TEXT
) RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'idx_rd_'
        || regexp_replace(lower(p_table_id), '[^a-z0-9]', '', 'g')
        || '_'
        || left(replace(p_column_id, '-', ''), 12);
$$;

-- ── Create the partial index for a column ──────────────────────────────────

CREATE OR REPLACE FUNCTION public.create_row_data_index(
    p_idx_name  TEXT,
    p_table_id  TEXT,
    p_column_id TEXT,
    p_col_type  TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Numeric-like: btree on cast-to-numeric for range queries.
    IF p_col_type IN ('number', 'date', 'datetime') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree (((row_data ->> %L)::NUMERIC)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    -- String-like single-value: btree on text extraction.
    ELSIF p_col_type IN ('text', 'select', 'email', 'url', 'phone', 'doc') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((row_data ->> %L)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    -- Container/array types: GIN on the JSONB value.
    ELSE
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING gin ((row_data -> %L)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    END IF;
END;
$$;

-- ── Drop the partial index ─────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.drop_row_data_index(
    p_idx_name TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE format('DROP INDEX IF EXISTS public.%I', p_idx_name);
END;
$$;

-- ── Grants ──────────────────────────────────────────────────────────────────

REVOKE ALL    ON
    FUNCTION public._build_rd_idx_name(TEXT, TEXT)                FROM public;
REVOKE ALL    ON
    FUNCTION public.create_row_data_index(TEXT, TEXT, TEXT, TEXT) FROM public;
REVOKE ALL    ON
    FUNCTION public.drop_row_data_index(TEXT)                     FROM public;

GRANT EXECUTE ON
    FUNCTION public._build_rd_idx_name(TEXT, TEXT)                TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.create_row_data_index(TEXT, TEXT, TEXT, TEXT) TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.drop_row_data_index(TEXT)                     TO app, mgr;
