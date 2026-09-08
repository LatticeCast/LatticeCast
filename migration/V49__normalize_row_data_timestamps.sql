-- upgrade
-- Make the canonical epoch-ms form (V48) the only form that can exist
-- in rows.row_data, in one atomic step. Three things must land together
-- and in this order:
--
--   1. normalisation on the write path -- from here on every inbound
--      date/datetime cell is converted, whatever shape it arrived in;
--   2. backfill of existing cells;
--   3. index rebuild onto ((row_data ->> col)::BIGINT).
--
-- Splitting them is not an option. Backfilling before normalising
-- leaves a window in which a client re-pollutes the rows just cleaned,
-- and nothing scans them again afterwards. Normalising before
-- backfilling leaves legacy strings in place, and step 3's CREATE INDEX
-- evaluates its expression over every row -- one surviving string and
-- the index build fails outright, which is the same failure V18
-- documented for the earlier ::NUMERIC case.
--
-- Rather than change _validate_row_data_mutation's return contract
-- (put_row_data depends on the columns array it returns for blob-cell
-- preservation), normalisation gets its own named function and both
-- mutation entry points call it right after validation.

-- ── Normalisation, applied at the single write choke point ──────────────

CREATE OR REPLACE FUNCTION public._normalize_row_data_timestamps(
    p_columns JSONB,
    p_data    JSONB
) RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT p_data || coalesce(
        (
            SELECT jsonb_object_agg(
                column_data ->> 'column_id',
                public.to_canonical_epoch_ms(
                    p_data -> (column_data ->> 'column_id'),
                    column_data ->> 'type'
                )
            )
            FROM jsonb_array_elements(p_columns) AS column_data
            WHERE column_data ->> 'type' IN ('date', 'datetime')
            AND   p_data ? (column_data ->> 'column_id')
        ),
        '{}'::JSONB
    );
$$;

REVOKE ALL    ON
    FUNCTION public._normalize_row_data_timestamps(JSONB, JSONB) FROM public;
GRANT EXECUTE ON
    FUNCTION public._normalize_row_data_timestamps(JSONB, JSONB) TO app, mgr;

-- ── Row mutations normalise before writing ──────────────────────────────
-- Both stay SECURITY INVOKER (V45) so the rows RLS policies govern them.

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
    v_by      UUID;
    v_columns JSONB;
    v_row     public.rows;
BEGIN
    v_columns := public._validate_row_data_mutation(
        p_workspace_id, p_table_id, p_patch
    );
    p_patch := public._normalize_row_data_timestamps(v_columns, p_patch);
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
    p_data := public._normalize_row_data_timestamps(v_columns, p_data);
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

REVOKE ALL    ON
    FUNCTION public.patch_row_data(UUID, VARCHAR, BIGINT, JSONB) FROM public;
REVOKE ALL    ON
    FUNCTION public.put_row_data(UUID, VARCHAR, BIGINT, JSONB) FROM public;
GRANT EXECUTE ON
    FUNCTION public.patch_row_data(UUID, VARCHAR, BIGINT, JSONB) TO app;
GRANT EXECUTE ON
    FUNCTION public.put_row_data(UUID, VARCHAR, BIGINT, JSONB) TO app;

-- ── Future date/datetime columns index on the epoch integer ─────────────
-- Same guards as V47; only the date/datetime branch changes, so a column
-- added after this migration does not recreate the retired ISO index.

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
            'USING btree (((row_data ->> %L)::BIGINT)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_workspace_id, p_table_id
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

-- ── Retire old timestamp-expression indexes before changing their input ──
-- An UPDATE that replaces an ISO string with an epoch integer also updates
-- every existing index on that row. V18's expression indexes call
-- immutable_iso_to_ts(text), so they must be dropped before the backfill:
-- otherwise PostgreSQL tries to parse the new integer as a timestamp while
-- maintaining the old index.

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT index_namespace.nspname AS schema_name,
               index_data.relname    AS index_name
        FROM   pg_index AS index_definition
        INNER JOIN pg_class AS index_data
            ON index_data.oid = index_definition.indexrelid
        INNER JOIN pg_namespace AS index_namespace
            ON index_namespace.oid = index_data.relnamespace
        WHERE  pg_get_indexdef(index_definition.indexrelid)
               LIKE '%immutable_iso_to_ts(%'
    LOOP
        EXECUTE format('DROP INDEX %I.%I', r.schema_name, r.index_name);
    END LOOP;
END;
$$;

-- ── Backfill existing cells ──────────────────────────────────────────────
-- Fail closed. If a legacy cell cannot be parsed, _parse_legacy_ts_ms
-- raises with the offending text and the whole migration aborts. That is
-- deliberate: silently coercing an unreadable value to NULL would
-- destroy data, and this project already has one data-destruction
-- incident on record (2026-05-15, see the db-sql skill).

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_data.workspace_id,
               table_data.table_id,
               column_data ->> 'column_id' AS column_id,
               column_data ->> 'type'      AS col_type
        FROM   public.tables AS table_data
        CROSS JOIN LATERAL
            jsonb_array_elements(table_data.config -> 'columns') AS column_data
        WHERE  column_data ->> 'type' IN ('date', 'datetime')
    LOOP
        UPDATE public.rows
        SET    row_data = jsonb_set(
                   row_data,
                   ARRAY[r.column_id],
                   public.to_canonical_epoch_ms(
                       row_data -> r.column_id,
                       r.col_type
                   ),
                   TRUE
               )
        WHERE  workspace_id = r.workspace_id
        AND    table_id     = r.table_id
        AND    row_data ? r.column_id;
    END LOOP;
END;
$$;

-- ── The invariant belongs to the table, not to two functions ───────────
-- patch_row_data and put_row_data are not the only way row_data is
-- written. RowRepository.create() (repository/row.py:29-38) issues a
-- raw INSERT INTO rows (..., row_data, ...), so row *creation* never
-- passed through either function and never got normalised. mgr tooling
-- and direct SQL bypass them as well. A trigger is the only place the
-- invariant actually holds for every writer.
--
-- SECURITY DEFINER on purpose: it reads public.tables, which is
-- RLS-protected. Under SECURITY INVOKER a caller who could not see the
-- table row would read a NULL config and silently skip normalisation --
-- fail-open on the exact guarantee this migration exists to provide.
--
-- Two BEFORE triggers now sit on public.rows, and PostgreSQL fires
-- same-event triggers in name order: trg_rows_canonical_ts before
-- V51's trg_rows_row_id. They touch different columns, so the order is
-- irrelevant; it is pinned by naming rather than left to chance.
--
-- Normalisation is idempotent, so the overlap with patch_row_data and
-- put_row_data costs a re-check, not a wrong value: a canonical number
-- maps to itself and a midnight-aligned date stays aligned.

CREATE OR REPLACE FUNCTION public.trg_canonical_row_data_ts_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
BEGIN
    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = NEW.workspace_id
    AND    table_id     = NEW.table_id;

    IF v_columns IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.row_data := public._normalize_row_data_timestamps(
        v_columns, NEW.row_data
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rows_canonical_ts ON public.rows;
CREATE TRIGGER trg_rows_canonical_ts
BEFORE INSERT OR UPDATE OF row_data ON public.rows
FOR EACH ROW EXECUTE FUNCTION public.trg_canonical_row_data_ts_fn();

REVOKE ALL    ON
    FUNCTION public.trg_canonical_row_data_ts_fn() FROM public;
GRANT EXECUTE ON
    FUNCTION public.trg_canonical_row_data_ts_fn() TO app, mgr;

-- ── Rebuild existing date/datetime indexes onto the epoch integer ───────

DO $$
DECLARE
    r          RECORD;
    v_idx_name TEXT;
BEGIN
    FOR r IN
        SELECT table_data.workspace_id,
               table_data.table_id,
               column_data ->> 'column_id' AS column_id
        FROM   public.tables AS table_data
        CROSS JOIN LATERAL
            jsonb_array_elements(table_data.config -> 'columns') AS column_data
        WHERE  column_data ->> 'type' IN ('date', 'datetime')
    LOOP
        v_idx_name := public._build_rd_idx_name(
            r.workspace_id, r.table_id, r.column_id
        );
        EXECUTE format('DROP INDEX IF EXISTS public.%I', v_idx_name);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree (((row_data ->> %L)::BIGINT)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            v_idx_name, r.column_id, r.workspace_id, r.table_id
        );
    END LOOP;
END;
$$;

-- public.immutable_iso_to_ts (V18) is left in place, not dropped: no
-- date/datetime index references it after this migration, but dropping
-- a function this migration has not traced every caller of would be a
-- second change hiding inside this one.

-- ── Retire V11's pre-workspace-scoped index helpers ─────────────────────
-- V47 added workspace_id to all three signatures. Because the argument
-- lists differ, CREATE OR REPLACE made new functions and left V11's
-- originals in place as overloads. V47 already revoked EXECUTE on two
-- of them from app and mgr (V47:134-135), and the active add_column /
-- delete_column call the new arities (V47:41-44, V47:77-80), so nothing
-- reaches them -- but _build_rd_idx_name(TEXT, TEXT) is still granted
-- to app from V11:92, because V47 only revoked the three-argument form.
--
-- They are dead surface either way, and one of them would still build a
-- date index on the retired immutable_iso_to_ts expression if anything
-- ever did call it. Drop all three.

DROP FUNCTION IF EXISTS public.create_row_data_index(TEXT, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.drop_row_data_index(TEXT);
DROP FUNCTION IF EXISTS public._build_rd_idx_name(TEXT, TEXT);
