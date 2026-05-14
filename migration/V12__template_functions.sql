-- upgrade
-- Template seeders + thin dispatcher used by the BE to create a table
-- from a template kind ('blank' / 'pm' / 'crm').
--
-- Each _seed_<kind>:
--   1. Builds its column array (each column gets a fresh UUID column_id)
--   2. INSERTs view rows into public.table_views (view_id auto-assigned
--      by trg_set_view_id; name/type live inside config JSONB)
--   3. Returns JSONB = {columns, view_order, default_view} where
--      view_order is a list of view_id numbers and default_view is a
--      single view_id (or null for 'blank')
--
-- create_table_from_template (the BE-facing interface):
--   1. INSERTs into public.tables (trigger creates empty table_schemas)
--   2. Dispatches to _seed_<kind> via explicit CASE
--   3. PERFORMs create_row_data_index per column
--   4. UPDATEs the table_schemas row with the seed result
--
-- To add a new template (e.g. 'support'):
--   - Write _seed_support(ws, tid, by) returning the same JSONB shape
--   - Add `WHEN 'support' THEN v_result := _seed_support(...);` below.

-- ── Column-dict helpers (used here AND by V13 schema mutation funcs) ────────

CREATE OR REPLACE FUNCTION public._build_column_dict(
    p_name    TEXT,
    p_type    TEXT,
    p_options JSONB
) RETURNS JSONB
LANGUAGE sql
AS $$
    SELECT jsonb_build_object(
        'column_id', gen_random_uuid()::TEXT,
        'name',      p_name,
        'type',      p_type,
        'options',   COALESCE(p_options, '{}'::JSONB)
    );
$$;

CREATE OR REPLACE FUNCTION public._columns_name_map(p_columns JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT jsonb_object_agg(c ->> 'name', c ->> 'column_id')
    FROM jsonb_array_elements(p_columns) AS c;
$$;

REVOKE ALL    ON FUNCTION public._build_column_dict(TEXT, TEXT, JSONB) FROM public;
REVOKE ALL    ON FUNCTION public._columns_name_map(JSONB)              FROM public;
GRANT EXECUTE ON FUNCTION public._build_column_dict(TEXT, TEXT, JSONB) TO app, mgr;
GRANT EXECUTE ON FUNCTION public._columns_name_map(JSONB)              TO app, mgr;

-- ── _seed_blank ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public._seed_blank(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
BEGIN
    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text', '{}'::JSONB),
        _build_column_dict('Doc',         'doc',  '{}'::JSONB),
        _build_column_dict('Description', 'text', '{}'::JSONB)
    );
    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   '[]'::JSONB,
        'default_view', NULL::JSONB
    );
END;
$$;

-- ── _seed_pm ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public._seed_pm(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns         JSONB;
    v_col_ids         JSONB;
    v_view_id_sprint  BIGINT;
    v_view_id_roadmap BIGINT;
BEGIN
    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text',   '{}'::JSONB),
        _build_column_dict('Doc',         'doc',    '{}'::JSONB),
        _build_column_dict('Type',        'select',
            '{"choices":[
                {"value":"epic","color":"#a78bfa"},
                {"value":"story","color":"#60a5fa"},
                {"value":"task","color":"#4ade80"},
                {"value":"bug","color":"#f87171"}
            ]}'::JSONB),
        _build_column_dict('Status',      'select',
            '{"choices":[
                {"value":"todo","color":"#9ca3af"},
                {"value":"in_progress","color":"#60a5fa"},
                {"value":"testing","color":"#a78bfa"},
                {"value":"debugging","color":"#f87171"},
                {"value":"review","color":"#facc15"},
                {"value":"done","color":"#4ade80"},
                {"value":"merged","color":"#34d399"}
            ]}'::JSONB),
        _build_column_dict('Priority',    'select',
            '{"choices":[
                {"value":"critical","color":"#ef4444"},
                {"value":"high","color":"#f97316"},
                {"value":"medium","color":"#facc15"},
                {"value":"low","color":"#9ca3af"}
            ]}'::JSONB),
        _build_column_dict('Assignee',    'text',   '{}'::JSONB),
        _build_column_dict('Start Date',  'date',   '{}'::JSONB),
        _build_column_dict('Due Date',    'date',   '{}'::JSONB),
        _build_column_dict('Estimate',    'number', '{}'::JSONB),
        _build_column_dict('Tags',        'tags',   '{}'::JSONB),
        _build_column_dict('Description', 'text',   '{}'::JSONB),
        _build_column_dict('Parent',      'text',   '{}'::JSONB)
    );
    v_col_ids := _columns_name_map(v_columns);

    -- Sprint Board (kanban)
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id,
        jsonb_build_object(
            'name', 'Sprint Board',
            'type', 'kanban',
            'group_by', v_col_ids ->> 'Status',
            'card_fields', jsonb_build_array(
                v_col_ids ->> 'Title',
                v_col_ids ->> 'Priority',
                v_col_ids ->> 'Assignee'
            )
        ),
        p_by, p_by
    ) RETURNING view_id INTO v_view_id_sprint;

    -- Roadmap (timeline)
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id,
        jsonb_build_object(
            'name', 'Roadmap',
            'type', 'timeline',
            'start_col', v_col_ids ->> 'Start Date',
            'end_col',   v_col_ids ->> 'Due Date',
            'color_by',  v_col_ids ->> 'Status',
            'group_by',  v_col_ids ->> 'Type'
        ),
        p_by, p_by
    ) RETURNING view_id INTO v_view_id_roadmap;

    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   jsonb_build_array(v_view_id_sprint, v_view_id_roadmap),
        'default_view', to_jsonb(v_view_id_sprint)
    );
END;
$$;

-- ── _seed_crm ───────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public._seed_crm(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns           JSONB;
    v_col_ids           JSONB;
    v_view_id_pipeline  BIGINT;
    v_view_id_dashboard BIGINT;
BEGIN
    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text',   '{}'::JSONB),
        _build_column_dict('Doc',         'doc',    '{}'::JSONB),
        _build_column_dict('Stage',       'select',
            '{"choices":[
                {"value":"lead","color":"#9ca3af"},
                {"value":"qualified","color":"#60a5fa"},
                {"value":"proposal","color":"#facc15"},
                {"value":"won","color":"#4ade80"},
                {"value":"lost","color":"#f87171"}
            ]}'::JSONB),
        _build_column_dict('Value',       'number', '{}'::JSONB),
        _build_column_dict('Owner',       'text',   '{}'::JSONB),
        _build_column_dict('Close Date',  'date',   '{}'::JSONB),
        _build_column_dict('Tags',        'tags',   '{}'::JSONB),
        _build_column_dict('Description', 'text',   '{}'::JSONB)
    );
    v_col_ids := _columns_name_map(v_columns);

    -- Pipeline (kanban)
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id,
        jsonb_build_object(
            'name', 'Pipeline',
            'type', 'kanban',
            'group_by', v_col_ids ->> 'Stage',
            'card_fields', jsonb_build_array(
                v_col_ids ->> 'Title',
                v_col_ids ->> 'Value',
                v_col_ids ->> 'Owner'
            )
        ),
        p_by, p_by
    ) RETURNING view_id INTO v_view_id_pipeline;

    -- Sales Dashboard (dashboard)
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id,
        jsonb_build_object(
            'name', 'Sales Dashboard',
            'type', 'dashboard',
            'layout', jsonb_build_array(
                jsonb_build_object('id', 'pipeline_value', 'x', 0, 'y', 0, 'w', 3, 'h', 2),
                jsonb_build_object('id', 'by_stage',       'x', 3, 'y', 0, 'w', 6, 'h', 4),
                jsonb_build_object('id', 'by_owner',       'x', 9, 'y', 0, 'w', 3, 'h', 4),
                jsonb_build_object('id', 'won_value',      'x', 0, 'y', 2, 'w', 3, 'h', 2),
                jsonb_build_object('id', 'recent',         'x', 0, 'y', 4, 'w', 12, 'h', 4)
            ),
            'blocks', jsonb_build_object(
                'pipeline_value', jsonb_build_object(
                    'kind', 'number', 'title', 'Pipeline Value',
                    'lql', format(
                        'table(%L) | filter((r)->{r.stage in @["lead","qualified","proposal"]}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'field', 'value', 'format', '$,.0f'
                ),
                'by_stage', jsonb_build_object(
                    'kind', 'chart', 'title', 'Value by Stage',
                    'lql', format(
                        'table(%L) | group_by((r)->{r.stage}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'echarts', jsonb_build_object(
                        'dataset', jsonb_build_array(jsonb_build_object('$inject', 'rows')),
                        'xAxis', jsonb_build_object('type', 'category'),
                        'yAxis', jsonb_build_object('type', 'value'),
                        'series', jsonb_build_array(jsonb_build_object(
                            'type', 'bar',
                            'encode', jsonb_build_object('x', 'dim_0', 'y', 'value')
                        ))
                    )
                ),
                'by_owner', jsonb_build_object(
                    'kind', 'chart', 'title', 'Deals by Owner',
                    'lql', format(
                        'table(%L) | group_by((r)->{r.owner}) | aggregate(count())',
                        p_table_id
                    ),
                    'echarts', jsonb_build_object(
                        'dataset', jsonb_build_array(jsonb_build_object('$inject', 'rows')),
                        'xAxis', jsonb_build_object('type', 'category'),
                        'yAxis', jsonb_build_object('type', 'value'),
                        'series', jsonb_build_array(jsonb_build_object(
                            'type', 'bar',
                            'encode', jsonb_build_object('x', 'dim_0', 'y', 'count')
                        ))
                    )
                ),
                'won_value', jsonb_build_object(
                    'kind', 'number', 'title', 'Won Value',
                    'lql', format(
                        'table(%L) | filter((r)->{r.stage=="won"}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'field', 'value', 'format', '$,.0f'
                ),
                'recent', jsonb_build_object(
                    'kind', 'list', 'title', 'Recent Deals',
                    'lql', format('table(%L) | limit(10)', p_table_id),
                    'columns', '[]'::JSONB
                )
            )
        ),
        p_by, p_by
    ) RETURNING view_id INTO v_view_id_dashboard;

    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   jsonb_build_array(v_view_id_pipeline, v_view_id_dashboard),
        'default_view', to_jsonb(v_view_id_pipeline)
    );
END;
$$;

-- ── create_table_from_template (thin dispatcher) ────────────────────────────

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
    -- 1. Insert table — trigger trg_tables_create_table_schema creates
    --    the empty table_schemas row.
    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    -- 2. Dispatch to _seed_<kind>(ws, tid, by). Explicit CASE — adding
    --    a new kind = write _seed_X(...) AND add one WHEN line here.
    CASE p_kind
        WHEN 'blank' THEN
            v_result := _seed_blank(p_workspace_id, p_table_id, p_by);
        WHEN 'pm' THEN
            v_result := _seed_pm(p_workspace_id, p_table_id, p_by);
        WHEN 'crm' THEN
            v_result := _seed_crm(p_workspace_id, p_table_id, p_by);
        ELSE
            RAISE EXCEPTION 'unknown template kind: %', p_kind;
    END CASE;

    -- 3. Per-column indexes for filterable types.
    FOR v_col IN
        SELECT * FROM jsonb_array_elements(v_result -> 'columns')
    LOOP
        v_col_id   := v_col ->> 'column_id';
        v_col_type := v_col ->> 'type';
        IF v_col_type IN (
            'number', 'date', 'datetime',
            'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := _build_rd_idx_name(p_table_id::TEXT, v_col_id);
            PERFORM create_row_data_index(
                v_idx_name, p_table_id::TEXT, v_col_id, v_col_type
            );
        END IF;
    END LOOP;

    -- 4. Single UPDATE on the schemas row with the assembled config.
    UPDATE public.table_schemas
    SET    config     = v_result,
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;
END;
$$;

REVOKE ALL    ON
    FUNCTION public._seed_blank(UUID, VARCHAR, UUID)                         FROM public;
REVOKE ALL    ON
    FUNCTION public._seed_pm(UUID, VARCHAR, UUID)                            FROM public;
REVOKE ALL    ON
    FUNCTION public._seed_crm(UUID, VARCHAR, UUID)                           FROM public;
REVOKE ALL    ON
    FUNCTION public.create_table_from_template(UUID, VARCHAR, VARCHAR, UUID) FROM public;

GRANT EXECUTE ON
    FUNCTION public._seed_blank(UUID, VARCHAR, UUID)                         TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public._seed_pm(UUID, VARCHAR, UUID)                            TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public._seed_crm(UUID, VARCHAR, UUID)                           TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.create_table_from_template(UUID, VARCHAR, VARCHAR, UUID) TO app, mgr;
