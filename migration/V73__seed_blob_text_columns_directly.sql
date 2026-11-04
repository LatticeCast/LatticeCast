-- Emit current blob text columns directly from all table templates.
-- Replaces legacy doc-producing seed functions and the dispatcher conversion.

CREATE OR REPLACE FUNCTION public._seed_blank(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB;
BEGIN
    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text', '{}'::JSONB),
        _build_column_dict('Doc',         'blob', '{"kind":"text"}'::JSONB),
        _build_column_dict('Description', 'text', '{}'::JSONB)
    );
    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   '[]'::JSONB,
        'default_view', NULL::JSONB
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public._seed_crm(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_table_name TEXT;
    v_columns           JSONB;
    v_col_ids           JSONB;
    v_view_id_pipeline  BIGINT;
    v_view_id_dashboard BIGINT;
BEGIN
    SELECT table_name INTO v_table_name
    FROM   public.tables
    WHERE  table_id = p_table_id;

    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text',   '{}'::JSONB),
        _build_column_dict('Doc',         'blob',   '{"kind":"text"}'::JSONB),
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
        table_id, config, created_by, updated_by
    ) VALUES (
        p_table_id,
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
        table_id, config, created_by, updated_by
    ) VALUES (
        p_table_id,
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
                        'table(%I) | filter((r)->{r.stage in @["lead","qualified","proposal"]}) | aggregate(@{"value": sum(r.value)})',
                        v_table_name
                    ),
                    'field', 'value', 'format', '$,.0f'
                ),
                'by_stage', jsonb_build_object(
                    'kind', 'chart', 'title', 'Value by Stage',
                    'lql', format(
                        'table(%I) | group_by((r)->{r.stage}) | aggregate(@{"value": sum(r.value)})',
                        v_table_name
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
                        'table(%I) | group_by((r)->{r.owner}) | aggregate(count())',
                        v_table_name
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
                        'table(%I) | filter((r)->{r.stage=="won"}) | aggregate(@{"value": sum(r.value)})',
                        v_table_name
                    ),
                    'field', 'value', 'format', '$,.0f'
                ),
                'recent', jsonb_build_object(
                    'kind', 'list', 'title', 'Recent Deals',
                    'lql', format('table(%I) | limit(10)', v_table_name),
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
$function$;

CREATE OR REPLACE FUNCTION public._seed_pm(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_table_name TEXT;
    v_columns         JSONB;
    v_col_ids         JSONB;
    v_view_id_sprint  BIGINT;
    v_view_id_roadmap BIGINT;
BEGIN
    SELECT table_name INTO v_table_name
    FROM   public.tables
    WHERE  table_id = p_table_id;

    v_columns := jsonb_build_array(
        _build_column_dict('Title',       'text',   '{}'::JSONB),
        _build_column_dict('Doc',         'blob',   '{"kind":"text"}'::JSONB),
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

    INSERT INTO public.table_views (
        table_id, config, created_by, updated_by
    ) VALUES (
        p_table_id,
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

    INSERT INTO public.table_views (
        table_id, config, created_by, updated_by
    ) VALUES (
        p_table_id,
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
$function$;

CREATE OR REPLACE FUNCTION public.create_table_from_template(
    p_workspace_id uuid,
    p_table_name   varchar,
    p_kind         varchar,
    p_by           uuid
) RETURNS bigint
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $function$
DECLARE
    v_table_id BIGINT;
    v_result   JSONB;
    v_col      JSONB;
    v_col_id   TEXT;
    v_col_type TEXT;
    v_idx_name TEXT;
BEGIN
    -- The id is the database's to assign; the caller only names the table.
    INSERT INTO public.tables (workspace_id, table_name)
    VALUES (p_workspace_id, p_table_name)
    RETURNING table_id INTO v_table_id;

    CASE p_kind
        WHEN 'blank' THEN
            v_result := _seed_blank(p_workspace_id, v_table_id, p_by);
        WHEN 'pm' THEN
            v_result := _seed_pm(p_workspace_id, v_table_id, p_by);
        WHEN 'crm' THEN
            v_result := _seed_crm(p_workspace_id, v_table_id, p_by);
        WHEN 'workflow' THEN
            v_result := _seed_workflow(p_workspace_id, v_table_id, p_by);
        ELSE RAISE EXCEPTION 'unknown template kind: %', p_kind;
    END CASE;

    UPDATE public.tables
    SET config = v_result, updated_by = p_by, updated_at = now()
    WHERE table_id = v_table_id;

    FOR v_col IN SELECT * FROM jsonb_array_elements(v_result -> 'columns') LOOP
        v_col_id := v_col ->> 'column_id';
        v_col_type := v_col ->> 'type';
        IF v_col_type IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := public._build_rd_idx_name(
                p_workspace_id, v_table_id, v_col_id
            );
            PERFORM public.create_row_data_index(
                p_workspace_id, v_idx_name, v_table_id, v_col_id, v_col_type
            );
        END IF;
    END LOOP;

    RETURN v_table_id;
END;
$function$;
