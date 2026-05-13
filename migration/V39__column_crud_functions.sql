-- upgrade
-- V39: Column CRUD as PG functions.
--
-- Each of these touches two things atomically:
--   - the __schema__ row's JSONB column array (data write)
--   - per-column index DDL via SECURITY DEFINER `create_row_data_index` /
--     `drop_row_data_index` (DDL write)
--
-- A two-step write where step 2 is DDL is exactly where a PG function
-- earns its keep — Python orchestration today commits the JSONB write
-- before attempting the index, so a CREATE INDEX failure leaves a column
-- with no index. The function wraps both in one transaction.
--
-- Functions (all non-DEFINER, RLS context inherited from caller):
--   add_column     — append column to __schema__ + create index
--   update_column  — patch column; if type changed, swap the index
--   delete_column  — drop index + remove column from __schema__

-- ── Helper: build a single column object with a fresh UUID ───────────────
CREATE OR REPLACE FUNCTION _BUILD_COLUMN_DICT(
    p_name TEXT,
    p_type TEXT,
    p_options JSONB,
    p_position INT
)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
    SELECT JSONB_BUILD_OBJECT(
        'column_id', GEN_RANDOM_UUID()::TEXT,
        'name',      p_name,
        'type',      p_type,
        'options',   COALESCE(p_options, '{}'::JSONB),
        'position',  p_position,
        'created_at', NOW()
    );
$$;

GRANT EXECUTE ON FUNCTION _BUILD_COLUMN_DICT(TEXT, TEXT, JSONB, INT) TO app;

-- ── add_column ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ADD_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_name TEXT,
    p_type TEXT,
    p_options JSONB,
    p_position INT,
    p_created_by UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
    v_new_col JSONB;
    v_col_id TEXT;
    v_idx_name TEXT;
    v_position INT;
BEGIN
    SELECT config INTO v_columns
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'Table % not found (no __schema__ row)', p_table_id;
    END IF;
    IF JSONB_TYPEOF(v_columns) <> 'array' THEN
        v_columns := '[]'::JSONB;
    END IF;

    v_position := COALESCE(p_position, JSONB_ARRAY_LENGTH(v_columns));
    v_new_col := _BUILD_COLUMN_DICT(p_name, p_type, p_options, v_position);
    v_col_id := v_new_col->>'column_id';

    UPDATE public.table_views
    SET config = v_columns || JSONB_BUILD_ARRAY(v_new_col),
        updated_by = p_created_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    -- Mirrors BTREE_TYPES + GIN_TYPES in backend/src/repository/table.py.
    -- Unknown types no-op inside create_row_data_index.
    IF p_type IN ('number','date','select','tags','text','string','url','checkbox') THEN
        v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, v_col_id);
        PERFORM CREATE_ROW_DATA_INDEX(
            v_idx_name, p_table_id::TEXT, v_col_id, p_type
        );
    END IF;

    RETURN v_new_col;
END;
$$;

GRANT EXECUTE ON FUNCTION
ADD_COLUMN(UUID, VARCHAR, TEXT, TEXT, JSONB, INT, UUID) TO app;

-- ── update_column ───────────────────────────────────────────────────────
-- p_patch keys override the existing column's fields. column_id and
-- created_at are preserved. If p_patch.type differs from the existing
-- type, the index is swapped atomically.
CREATE OR REPLACE FUNCTION UPDATE_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_column_id TEXT,
    p_patch JSONB,
    p_updated_by UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
    v_idx INT;
    v_old_col JSONB;
    v_merged JSONB;
    v_new_columns JSONB := '[]'::JSONB;
    v_elem JSONB;
    v_new_type TEXT;
    v_idx_name TEXT;
BEGIN
    SELECT config INTO v_columns
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_columns IS NULL OR JSONB_TYPEOF(v_columns) <> 'array' THEN
        RAISE EXCEPTION 'Table % schema missing or malformed', p_table_id;
    END IF;

    v_idx := NULL;
    FOR v_idx IN
        SELECT ord - 1
        FROM JSONB_ARRAY_ELEMENTS(v_columns) WITH ORDINALITY AS t(elem, ord)
        WHERE elem->>'column_id' = p_column_id
        LIMIT 1
    LOOP
        v_old_col := v_columns->v_idx;
    END LOOP;

    IF v_old_col IS NULL THEN
        RAISE EXCEPTION 'Column % not found in %', p_column_id, p_table_id;
    END IF;

    v_merged := v_old_col || (p_patch - 'column_id' - 'created_at');
    v_merged := JSONB_SET(v_merged, ARRAY['column_id'], v_old_col->'column_id');
    IF v_old_col ? 'created_at' THEN
        v_merged := JSONB_SET(
            v_merged, ARRAY['created_at'], v_old_col->'created_at'
        );
    END IF;

    FOR v_elem IN
        SELECT
            CASE WHEN (ord - 1) = v_idx THEN v_merged ELSE elem END
        FROM JSONB_ARRAY_ELEMENTS(v_columns) WITH ORDINALITY AS t(elem, ord)
        ORDER BY ord
    LOOP
        v_new_columns := v_new_columns || JSONB_BUILD_ARRAY(v_elem);
    END LOOP;

    UPDATE public.table_views
    SET config = v_new_columns,
        updated_by = p_updated_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    v_new_type := v_merged->>'type';
    IF v_new_type IS NOT NULL AND v_new_type <> COALESCE(v_old_col->>'type', '') THEN
        v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, p_column_id);
        PERFORM DROP_ROW_DATA_INDEX(v_idx_name);
        IF v_new_type IN ('number','date','select','tags','text','string','url','checkbox') THEN
            PERFORM CREATE_ROW_DATA_INDEX(
                v_idx_name, p_table_id::TEXT, p_column_id, v_new_type
            );
        END IF;
    END IF;

    RETURN v_merged;
END;
$$;

GRANT EXECUTE ON FUNCTION
UPDATE_COLUMN(UUID, VARCHAR, TEXT, JSONB, UUID) TO app;

-- ── delete_column ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION DELETE_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_column_id TEXT,
    p_updated_by UUID
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
    v_filtered JSONB;
    v_idx_name TEXT;
    v_removed_count INT;
BEGIN
    SELECT config INTO v_columns
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_columns IS NULL OR JSONB_TYPEOF(v_columns) <> 'array' THEN
        RAISE EXCEPTION 'Table % schema missing or malformed', p_table_id;
    END IF;

    SELECT COALESCE(JSONB_AGG(elem), '[]'::JSONB)
    INTO v_filtered
    FROM JSONB_ARRAY_ELEMENTS(v_columns) AS elem
    WHERE elem->>'column_id' <> p_column_id;

    v_removed_count := JSONB_ARRAY_LENGTH(v_columns) - JSONB_ARRAY_LENGTH(v_filtered);
    IF v_removed_count = 0 THEN
        RAISE EXCEPTION 'Column % not found in %', p_column_id, p_table_id;
    END IF;

    v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, p_column_id);
    PERFORM DROP_ROW_DATA_INDEX(v_idx_name);

    UPDATE public.table_views
    SET config = v_filtered,
        updated_by = p_updated_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';
END;
$$;

GRANT EXECUTE ON FUNCTION
DELETE_COLUMN(UUID, VARCHAR, TEXT, UUID) TO app;
