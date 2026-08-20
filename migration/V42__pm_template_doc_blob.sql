-- PM tables create their document column as a blob from the outset. V41
-- remains responsible for upgrading legacy persisted `doc` columns.

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
        _build_column_dict('Doc',         'blob',   '{"kind":"doc"}'::JSONB),
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
