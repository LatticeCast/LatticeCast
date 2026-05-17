-- V23: merge public.table_schemas into public.tables
--
-- table_schemas was always 1:1 with tables (same PK, auto-created by
-- trigger). This migration absorbs its columns (config, created_by,
-- updated_by) into public.tables and rewrites every function that
-- referenced the old table.

-- ── 1. Add columns ─────────────────────────────────────────────────

ALTER TABLE public.tables
ADD COLUMN IF NOT EXISTS config     JSONB NOT NULL
    DEFAULT '{"columns":[],"view_order":[],"default_view":null}'
    ::JSONB,
ADD COLUMN IF NOT EXISTS created_by UUID,
ADD COLUMN IF NOT EXISTS updated_by UUID;

-- ── 2. Copy data from table_schemas ────────────────────────────────

UPDATE public.tables AS t
SET    config     = ts.config,
       created_by = ts.created_by,
       updated_by = ts.updated_by
FROM   public.table_schemas AS ts
WHERE  t.workspace_id = ts.workspace_id
AND    t.table_id     = ts.table_id;

-- ── 3. Drop table_schemas infrastructure ───────────────────────────

DROP TRIGGER IF EXISTS trg_tables_create_table_schema
    ON public.tables;
DROP FUNCTION IF EXISTS public.trg_create_table_schema_fn();

DROP POLICY IF EXISTS table_schemas_workspace_member
    ON public.table_schemas;
DROP TABLE IF EXISTS public.table_schemas;

-- ── 4. Rewrite schema functions (V13/V22) ──────────────────────────

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

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

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
    v_new_cfg     JSONB;
    v_idx_name    TEXT;
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

    IF NOT EXISTS (
        SELECT 1
        FROM   jsonb_array_elements(v_old_columns) AS c
        WHERE  c ->> 'column_id' = p_column_id
    ) THEN
        RAISE EXCEPTION 'column not found: %', p_column_id;
    END IF;

    SELECT COALESCE(jsonb_agg(c), '[]'::JSONB)
    INTO   v_new_columns
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' <> p_column_id;

    UPDATE public.tables
    SET    config     = jsonb_set(
               config, '{columns}', v_new_columns
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    v_idx_name := _build_rd_idx_name(
        p_table_id::TEXT, p_column_id
    );
    PERFORM drop_row_data_index(v_idx_name);

    RETURN v_new_cfg;
END;
$$;

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
    SELECT ARRAY(
        SELECT jsonb_array_elements_text(p_order)
    ) INTO v_order_arr;

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
        c ORDER BY array_position(
            v_order_arr, c ->> 'column_id'
        )
    )
    INTO   v_new_columns
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' = ANY (v_order_arr);

    UPDATE public.tables
    SET    config     = jsonb_set(
               config, '{columns}',
               COALESCE(v_new_columns, '[]'::JSONB)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

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
    UPDATE public.tables
    SET    config     = jsonb_set(
               config, '{view_order}', p_order
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;

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
            RAISE EXCEPTION 'view_id not found: %',
                p_view_id;
        END IF;
    END IF;

    UPDATE public.tables
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
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;

-- ── 5. Rewrite view functions (V14/V19) ────────────────────────────

CREATE OR REPLACE FUNCTION public.create_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_config       JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_view_id BIGINT;
    v_new_cfg JSONB;
BEGIN
    INSERT INTO public.table_views (
        workspace_id, table_id, config,
        created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id, p_config, p_by, p_by
    ) RETURNING view_id INTO v_view_id;

    UPDATE public.tables
    SET    config = jsonb_set(
               config,
               '{view_order}',
               COALESCE(config -> 'view_order', '[]'::JSONB)
                   || to_jsonb(v_view_id)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_patch        JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_new_cfg JSONB;
    v_merged  JSONB;
    v_key     TEXT;
BEGIN
    SELECT config INTO v_merged
    FROM   public.table_views
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'view not found: %', p_view_id;
    END IF;

    FOR v_key IN SELECT key FROM jsonb_each(p_patch)
    LOOP
        IF (p_patch -> v_key) = 'null'::jsonb THEN
            v_merged := v_merged - v_key;
        ELSE
            v_merged := jsonb_set(
                v_merged, ARRAY[v_key], p_patch -> v_key
            );
        END IF;
    END LOOP;

    UPDATE public.table_views
    SET    config     = v_merged,
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id;

    SELECT config
    INTO   v_new_cfg
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    RETURN v_new_cfg;
END;
$$;

CREATE OR REPLACE FUNCTION public.delete_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_old_order   JSONB;
    v_new_order   JSONB;
    v_old_default JSONB;
    v_new_default JSONB;
    v_new_cfg     JSONB;
BEGIN
    DELETE FROM public.table_views
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'view not found: %', p_view_id;
    END IF;

    SELECT config -> 'view_order',
           config -> 'default_view'
    INTO   v_old_order, v_old_default
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    SELECT COALESCE(jsonb_agg(x), '[]'::JSONB)
    INTO   v_new_order
    FROM   jsonb_array_elements(
        COALESCE(v_old_order, '[]'::JSONB)
    ) AS x
    WHERE  (x)::TEXT::BIGINT <> p_view_id;

    IF v_old_default IS NOT NULL
        AND v_old_default <> 'null'::JSONB
        AND (v_old_default)::TEXT::BIGINT = p_view_id
    THEN
        v_new_default := 'null'::JSONB;
    ELSE
        v_new_default := v_old_default;
    END IF;

    UPDATE public.tables
    SET    config = jsonb_set(
               jsonb_set(
                   config, '{view_order}', v_new_order
               ),
               '{default_view}',
               COALESCE(v_new_default, 'null'::JSONB)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

-- ── 6. Rewrite create_table_from_template (V12) ────────────────────

CREATE OR REPLACE FUNCTION public.create_table_from_template(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_kind         VARCHAR,
    p_by           UUID
) RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_result   JSONB;
    v_col      JSONB;
    v_col_id   TEXT;
    v_col_type TEXT;
    v_idx_name TEXT;
BEGIN
    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    CASE p_kind
        WHEN 'blank' THEN
            v_result := _seed_blank(
                p_workspace_id, p_table_id, p_by
            );
        WHEN 'pm' THEN
            v_result := _seed_pm(
                p_workspace_id, p_table_id, p_by
            );
        WHEN 'crm' THEN
            v_result := _seed_crm(
                p_workspace_id, p_table_id, p_by
            );
        ELSE
            RAISE EXCEPTION 'unknown template kind: %',
                p_kind;
    END CASE;

    FOR v_col IN
        SELECT *
        FROM   jsonb_array_elements(v_result -> 'columns')
    LOOP
        v_col_id   := v_col ->> 'column_id';
        v_col_type := v_col ->> 'type';
        IF v_col_type IN (
            'number', 'date', 'datetime',
            'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := _build_rd_idx_name(
                p_table_id::TEXT, v_col_id
            );
            PERFORM create_row_data_index(
                v_idx_name, p_table_id::TEXT,
                v_col_id, v_col_type
            );
        END IF;
    END LOOP;

    UPDATE public.tables
    SET    config     = v_result,
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;
END;
$$;
