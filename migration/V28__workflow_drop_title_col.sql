-- V28: Remove Title column from workflow template.
-- The first column is now just 'name' (no separate Title).

CREATE OR REPLACE FUNCTION public._seed_workflow(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns       JSONB;
    v_col_ids       JSONB;
    v_view_id_wf    BIGINT;
BEGIN
    v_columns := jsonb_build_array(
        _build_column_dict('name',        'text',   '{}'::JSONB),
        _build_column_dict('type',        'select',
            '{"choices":[
                {"value":"START","color":"#15a74b"},
                {"value":"STEP","color":"#246ac0"},
                {"value":"TOOL","color":"#dbb726"},
                {"value":"CONDITION","color":"#744de7"},
                {"value":"INFO","color":"#9ca3af"},
                {"value":"SUBGRAPH","color":"#f97316"}
            ]}'::JSONB),
        _build_column_dict('description', 'text',   '{}'::JSONB),
        _build_column_dict('graph_name',  'select',
            '{"choices":[
                {"value":"root","color":"#9ca3af"}
            ]}'::JSONB),
        _build_column_dict('nexts',       'text',   '[]'::JSONB),
        _build_column_dict('true_next',   'text',   '{}'::JSONB),
        _build_column_dict('false_next',  'text',   '{}'::JSONB),
        _build_column_dict('pos_x',       'number', '{}'::JSONB),
        _build_column_dict('pos_y',       'number', '{}'::JSONB)
    );
    v_col_ids := _columns_name_map(v_columns);

    -- Workflow view (default)
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id,
        jsonb_build_object(
            'name', 'Workflow',
            'type', 'workflow'
        ),
        p_by, p_by
    ) RETURNING view_id INTO v_view_id_wf;

    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   jsonb_build_array(v_view_id_wf),
        'default_view', to_jsonb(v_view_id_wf)
    );
END;
$$;
