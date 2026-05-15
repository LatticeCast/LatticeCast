-- upgrade
-- Fix: create_row_data_index() lumped 'date'/'datetime' with 'number'
-- and cast row_data values to ::NUMERIC. Date columns store ISO-8601
-- strings ("2025-05-15"); ::NUMERIC cast raises an error on every row
-- insert into a table that has a date column.
--
-- Changes:
--   1. Add immutable_iso_to_ts() — IMMUTABLE text→TIMESTAMP wrapper
--      (IMMUTABLE is required for use in index expressions).
--   2. Replace create_row_data_index() — split 'number' (::NUMERIC)
--      from 'date'/'datetime' (immutable_iso_to_ts).
--   3. Rebuild existing broken date/datetime partial indexes.

-- ── 1. IMMUTABLE ISO-to-timestamp helper ────────────────────────────────────

CREATE OR REPLACE FUNCTION public.immutable_iso_to_ts(
    p_iso TEXT
) RETURNS TIMESTAMP
LANGUAGE sql
IMMUTABLE STRICT
AS $$
    SELECT p_iso::TIMESTAMP;
$$;

REVOKE ALL    ON
    FUNCTION public.immutable_iso_to_ts(TEXT) FROM public;
GRANT EXECUTE ON
    FUNCTION public.immutable_iso_to_ts(TEXT) TO app, mgr;

-- ── 2. Corrected create_row_data_index ──────────────────────────────────────

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
    -- Number: btree on cast-to-numeric for range queries.
    IF p_col_type = 'number' THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree (((row_data ->> %L)::NUMERIC)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    -- Date/datetime: btree on immutable ISO-to-timestamp cast.
    ELSIF p_col_type IN ('date', 'datetime') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree '
            '(public.immutable_iso_to_ts(row_data ->> %L)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    -- String-like single-value: btree on text extraction.
    ELSIF p_col_type IN (
        'text', 'select', 'email', 'url', 'phone', 'doc'
    ) THEN
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

-- ── 3. Rebuild existing broken date/datetime partial indexes ─────────────────
-- Drop the ::NUMERIC btree and recreate with immutable_iso_to_ts.
-- Iterates over every date/datetime column recorded in table_schemas.

DO $$
DECLARE
    r          RECORD;
    v_idx_name TEXT;
BEGIN
    FOR r IN
        SELECT ts.table_id,
               col ->> 'column_id' AS column_id
        FROM   public.table_schemas AS ts,
               jsonb_array_elements(ts.config -> 'columns') AS col
        WHERE  col ->> 'type' IN ('date', 'datetime')
    LOOP
        v_idx_name := public._build_rd_idx_name(r.table_id, r.column_id);
        EXECUTE format('DROP INDEX IF EXISTS public.%I', v_idx_name);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree '
            '(public.immutable_iso_to_ts(row_data ->> %L)) '
            'WHERE table_id = %L',
            v_idx_name, r.column_id, r.table_id
        );
    END LOOP;
END;
$$;
