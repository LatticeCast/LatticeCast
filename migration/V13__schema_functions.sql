-- upgrade
-- Mutation functions on public.table_schemas.config. All operate on the
-- single JSONB document {columns, view_order, default_view} and return
-- the full new config so the BE can hand it straight to the FE.
--
--   add_column            (ws, tid, name, type, options, by)   → config
--   update_column         (ws, tid, column_id, patch, by)      → config
--   delete_column         (ws, tid, column_id, by)             → config
--   update_col_order      (ws, tid, order_jsonb_array, by)     → config
--   update_view_order     (ws, tid, order_jsonb_array, by)     → config
--   update_default_view   (ws, tid, view_id_or_null, by)       → config
--
-- view_order entries are view_id (BIGINT); default_view is view_id or
-- null. col_order entries are column_id (UUID string).

-- ── add_column ──────────────────────────────────────────────────────────────

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
    v_new_col   JSONB;
    v_col_id    TEXT;
    v_new_cfg   JSONB;
    v_idx_name  TEXT;
BEGIN
    v_new_col := _build_column_dict(p_name, p_type, p_options);
    v_col_id  := v_new_col ->> 'column_id';

    UPDATE public.table_schemas
    SET    config = jsonb_set(
               config,
               '{columns}',
               COALESCE(config -> 'columns', '[]'::JSONB) || v_new_col
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    -- Create the filter index if the type is filterable.
    IF p_type IN (
        'number', 'date', 'datetime',
        'text', 'string', 'select', 'tags',
        'email', 'url', 'phone', 'checkbox'
    ) THEN
        v_idx_name := _build_rd_idx_name(p_table_id::TEXT, v_col_id);
        PERFORM create_row_data_index(
            v_idx_name, p_table_id::TEXT, v_col_id, p_type
        );
    END IF;

    RETURN v_new_cfg;
END;
$$;

-- ── update_column ───────────────────────────────────────────────────────────
-- Patch merges into the existing column dict. Caller must strip any
-- read-only keys (column_id, created_at) before passing the patch.

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
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_old_columns IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
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

    UPDATE public.table_schemas
    SET    config     = jsonb_set(config, '{columns}', v_new_columns),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

-- ── delete_column ───────────────────────────────────────────────────────────

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
    v_found       BOOLEAN := FALSE;
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

    SELECT COALESCE(jsonb_agg(c), '[]'::JSONB),
           bool_or(c ->> 'column_id' = p_column_id)
    INTO   v_new_columns, v_found
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' <> p_column_id;

    IF NOT v_found THEN
        RAISE EXCEPTION 'column not found: %', p_column_id;
    END IF;

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

-- ── update_col_order ────────────────────────────────────────────────────────
-- p_order is a JSONB array of column_id strings. Reorders config.columns
-- to match. Any column_id present in old config but missing from p_order
-- is dropped from the output.

CREATE OR REPLACE FUNCTION public.update_col_order(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_order        JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_order_arr   TEXT[];
    v_old_columns JSONB;
    v_new_columns JSONB;
    v_new_cfg     JSONB;
BEGIN
    SELECT ARRAY(SELECT jsonb_array_elements_text(p_order))
    INTO   v_order_arr;

    SELECT config -> 'columns'
    INTO   v_old_columns
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_old_columns IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    SELECT jsonb_agg(c ORDER BY array_position(v_order_arr, c ->> 'column_id'))
    INTO   v_new_columns
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' = ANY (v_order_arr);

    UPDATE public.table_schemas
    SET    config     = jsonb_set(config, '{columns}', COALESCE(v_new_columns, '[]'::JSONB)),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

-- ── update_view_order ───────────────────────────────────────────────────────
-- p_order is a JSONB array of view_id numbers.

CREATE OR REPLACE FUNCTION public.update_view_order(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_order        JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_new_cfg JSONB;
BEGIN
    UPDATE public.table_schemas
    SET    config     = jsonb_set(config, '{view_order}', p_order),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;

-- ── update_default_view ─────────────────────────────────────────────────────
-- p_view_id is a view_id number, or NULL to clear.

CREATE OR REPLACE FUNCTION public.update_default_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_exists  BOOLEAN;
    v_new_cfg JSONB;
BEGIN
    IF p_view_id IS NOT NULL THEN
        SELECT EXISTS (
            SELECT 1
            FROM   public.table_views
            WHERE  workspace_id = p_workspace_id
            AND    table_id     = p_table_id
            AND    view_id      = p_view_id
        ) INTO v_exists;
        IF NOT v_exists THEN
            RAISE EXCEPTION 'view_id not found: %', p_view_id;
        END IF;
    END IF;

    UPDATE public.table_schemas
    SET    config     = jsonb_set(
               config,
               '{default_view}',
               COALESCE(to_jsonb(p_view_id), 'null'::JSONB)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table_schemas row not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;

-- ── Grants ──────────────────────────────────────────────────────────────────

REVOKE ALL    ON
    FUNCTION public.add_column(UUID, VARCHAR, TEXT, TEXT, JSONB, UUID) FROM public;
REVOKE ALL    ON
    FUNCTION public.update_column(UUID, VARCHAR, TEXT, JSONB, UUID)    FROM public;
REVOKE ALL    ON
    FUNCTION public.delete_column(UUID, VARCHAR, TEXT, UUID)           FROM public;
REVOKE ALL    ON
    FUNCTION public.update_col_order(UUID, VARCHAR, JSONB, UUID)       FROM public;
REVOKE ALL    ON
    FUNCTION public.update_view_order(UUID, VARCHAR, JSONB, UUID)      FROM public;
REVOKE ALL    ON
    FUNCTION public.update_default_view(UUID, VARCHAR, BIGINT, UUID)   FROM public;

GRANT EXECUTE ON
    FUNCTION public.add_column(UUID, VARCHAR, TEXT, TEXT, JSONB, UUID) TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.update_column(UUID, VARCHAR, TEXT, JSONB, UUID)    TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.delete_column(UUID, VARCHAR, TEXT, UUID)           TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.update_col_order(UUID, VARCHAR, JSONB, UUID)       TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.update_view_order(UUID, VARCHAR, JSONB, UUID)      TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.update_default_view(UUID, VARCHAR, BIGINT, UUID)   TO app, mgr;
