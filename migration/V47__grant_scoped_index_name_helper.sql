-- Workspace-scoped index helpers and active column/template mutations.

-- ── Workspace-scoped index helpers ───────────────────────────────────────

CREATE OR REPLACE FUNCTION public._build_rd_idx_name(
    p_workspace_id UUID,
    p_table_id     TEXT,
    p_column_id    TEXT
) RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'idx_rd_'
        || left(replace(p_workspace_id::TEXT, '-', ''), 12)
        || '_'
        || left(regexp_replace(lower(p_table_id), '[^a-z0-9]', '', 'g'), 12)
        || '_'
        || left(replace(p_column_id, '-', ''), 12);
$$;

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
            'USING btree (public.immutable_iso_to_ts(row_data ->> %L)) '
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

CREATE OR REPLACE FUNCTION public.drop_row_data_index(
    p_workspace_id UUID,
    p_idx_name     TEXT,
    p_table_id     TEXT,
    p_column_id    TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id       UUID;
    v_legacy_idx_name TEXT;
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

    v_legacy_idx_name := public._build_rd_idx_name(p_table_id, p_column_id);
    EXECUTE format('DROP INDEX IF EXISTS public.%I', p_idx_name);
    EXECUTE format('DROP INDEX IF EXISTS public.%I', v_legacy_idx_name);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.create_row_data_index(TEXT, TEXT, TEXT, TEXT) FROM app, mgr;
REVOKE EXECUTE ON FUNCTION public.drop_row_data_index(TEXT) FROM app, mgr;
REVOKE ALL ON FUNCTION public._build_rd_idx_name(UUID, TEXT, TEXT) FROM public;
REVOKE ALL ON FUNCTION public.create_row_data_index(UUID, TEXT, TEXT, TEXT, TEXT) FROM public;
REVOKE ALL ON FUNCTION public.drop_row_data_index(UUID, TEXT, TEXT, TEXT) FROM public;
GRANT EXECUTE ON FUNCTION public.create_row_data_index(UUID, TEXT, TEXT, TEXT, TEXT) TO app;
GRANT EXECUTE ON FUNCTION public.drop_row_data_index(UUID, TEXT, TEXT, TEXT) TO app;
-- Active SECURITY INVOKER callers need the deterministic index-name helper.
GRANT EXECUTE ON FUNCTION public._build_rd_idx_name(UUID, TEXT, TEXT) TO app;

-- The current active template/column functions must use the scoped helpers.

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
    v_columns  JSONB;
    v_col      JSONB;
    v_col_id   TEXT;
    v_col_type TEXT;
    v_idx_name TEXT;
BEGIN
    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    CASE p_kind
        WHEN 'blank' THEN v_result := _seed_blank(p_workspace_id, p_table_id, p_by);
        WHEN 'pm' THEN v_result := _seed_pm(p_workspace_id, p_table_id, p_by);
        WHEN 'crm' THEN v_result := _seed_crm(p_workspace_id, p_table_id, p_by);
        WHEN 'workflow' THEN v_result := _seed_workflow(p_workspace_id, p_table_id, p_by);
        ELSE RAISE EXCEPTION 'unknown template kind: %', p_kind;
    END CASE;

    SELECT jsonb_agg(
        CASE
            WHEN column_entry.column_data ->> 'type' = 'doc' THEN jsonb_set(
                jsonb_set(column_entry.column_data, '{type}', '"blob"'::JSONB),
                '{options}', coalesce(column_entry.column_data -> 'options', '{}'::JSONB)
                    || '{"kind":"doc"}'::JSONB
            )
            ELSE column_entry.column_data
        END
        ORDER BY column_entry.ordinality
    )
    INTO v_columns
    FROM jsonb_array_elements(v_result -> 'columns')
        WITH ORDINALITY AS column_entry(column_data, ordinality);
    v_result := jsonb_set(v_result, '{columns}', v_columns);

    UPDATE public.tables
    SET config = v_result, updated_by = p_by, updated_at = now()
    WHERE workspace_id = p_workspace_id AND table_id = p_table_id;

    FOR v_col IN SELECT * FROM jsonb_array_elements(v_result -> 'columns') LOOP
        v_col_id := v_col ->> 'column_id';
        v_col_type := v_col ->> 'type';
        IF v_col_type IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := public._build_rd_idx_name(p_workspace_id, p_table_id, v_col_id);
            PERFORM public.create_row_data_index(
                p_workspace_id, v_idx_name, p_table_id, v_col_id, v_col_type
            );
        END IF;
    END LOOP;
END;
$$;

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
    v_columns JSONB;
    v_new_col JSONB;
    v_col_id TEXT;
    v_new_cfg JSONB;
    v_idx_name TEXT;
BEGIN
    SELECT config -> 'columns' INTO v_columns
    FROM public.tables WHERE workspace_id = p_workspace_id AND table_id = p_table_id;
    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    v_new_col := _build_column_dict(p_name, p_type, p_options);
    v_col_id := v_new_col ->> 'column_id';
    IF NOT public._column_names_are_unique(v_columns || v_new_col) THEN
        RAISE EXCEPTION 'duplicate normalized column name' USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE public.tables
    SET config = jsonb_set(config, '{columns}', coalesce(config -> 'columns', '[]'::JSONB) || v_new_col),
        updated_by = p_by, updated_at = now()
    WHERE workspace_id = p_workspace_id AND table_id = p_table_id
    RETURNING config INTO v_new_cfg;

    IF p_type IN (
        'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
        'email', 'url', 'phone', 'checkbox'
    ) THEN
        v_idx_name := public._build_rd_idx_name(p_workspace_id, p_table_id, v_col_id);
        PERFORM public.create_row_data_index(
            p_workspace_id, v_idx_name, p_table_id, v_col_id, p_type
        );
    END IF;
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
    v_new_cfg JSONB;
    v_idx_name TEXT;
BEGIN
    SELECT config -> 'columns' INTO v_old_columns
    FROM public.tables WHERE workspace_id = p_workspace_id AND table_id = p_table_id;
    IF v_old_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(v_old_columns) AS column_data
        WHERE column_data ->> 'column_id' = p_column_id
    ) THEN
        RAISE EXCEPTION 'column not found: %', p_column_id;
    END IF;

    v_idx_name := public._build_rd_idx_name(p_workspace_id, p_table_id, p_column_id);
    PERFORM public.drop_row_data_index(
        p_workspace_id, v_idx_name, p_table_id, p_column_id
    );

    SELECT coalesce(jsonb_agg(column_data), '[]'::JSONB) INTO v_new_columns
    FROM jsonb_array_elements(v_old_columns) AS column_data
    WHERE column_data ->> 'column_id' <> p_column_id;
    UPDATE public.tables
    SET config = jsonb_set(config, '{columns}', v_new_columns),
        updated_by = p_by, updated_at = now()
    WHERE workspace_id = p_workspace_id AND table_id = p_table_id
    RETURNING config INTO v_new_cfg;
    RETURN v_new_cfg;
END;
$$;
