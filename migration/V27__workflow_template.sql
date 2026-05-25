-- V27: Workflow template — _seed_workflow + dispatcher update.
--
-- Creates columns for node-graph modeling (name, type, description,
-- graph_name, nexts, true_next, false_next, pos_x, pos_y) and a
-- default Workflow view. Follows the same pattern as _seed_pm/_seed_crm.

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
        _build_column_dict('Title',       'text',   '{}'::JSONB),
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

-- ── Update dispatcher to include 'workflow' ─────────────────────────

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
        WHEN 'workflow' THEN
            v_result := _seed_workflow(
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

-- ── Grants ──────────────────────────────────────────────────────────

REVOKE ALL    ON
    FUNCTION public._seed_workflow(UUID, VARCHAR, UUID) FROM public;

GRANT EXECUTE ON
    FUNCTION public._seed_workflow(UUID, VARCHAR, UUID) TO app, mgr;
