-- upgrade
-- V69: rebind the table-scoped functions, triggers, policies and grants
-- to the new BIGINT identity.
--
-- Every function that took a VARCHAR table_id is dropped and recreated
-- with BIGINT rather than left as a second overload: after the cutover
-- there is exactly one table identity, and a stale slug overload would
-- silently resolve nothing (design.md section 5.5).
--
-- Bodies that build SQL or LQL keep working; only the index-name
-- derivation and the template seeder needed a real change.



DROP FUNCTION IF EXISTS public._build_rd_idx_name(text, text);

CREATE OR REPLACE FUNCTION public._build_rd_idx_name(p_table_id bigint, p_column_id text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT 'idx_rd_'
        || p_table_id::TEXT
        || '_'
        || left(replace(p_column_id, '-', ''), 12);
$function$;


DROP FUNCTION IF EXISTS public._build_rd_idx_name(uuid, text, text);

CREATE OR REPLACE FUNCTION public._build_rd_idx_name(p_workspace_id uuid, p_table_id bigint, p_column_id text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT 'idx_rd_'
        || left(replace(p_workspace_id::TEXT, '-', ''), 12)
        || '_'
        || p_table_id::TEXT
        || '_'
        || left(replace(p_column_id, '-', ''), 12);
$function$;


DROP FUNCTION IF EXISTS public._seed_blank(uuid, character varying, uuid);

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
        _build_column_dict('Doc',         'doc',  '{}'::JSONB),
        _build_column_dict('Description', 'text', '{}'::JSONB)
    );
    RETURN jsonb_build_object(
        'columns',      v_columns,
        'view_order',   '[]'::JSONB,
        'default_view', NULL::JSONB
    );
END;
$function$;


DROP FUNCTION IF EXISTS public._seed_crm(uuid, character varying, uuid);

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


DROP FUNCTION IF EXISTS public._seed_pm(uuid, character varying, uuid);

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
$function$;


DROP FUNCTION IF EXISTS public._seed_workflow(uuid, character varying, uuid);

CREATE OR REPLACE FUNCTION public._seed_workflow(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public._validate_row_data_mutation(uuid, character varying, jsonb);

CREATE OR REPLACE FUNCTION public._validate_row_data_mutation(p_workspace_id uuid, p_table_id bigint, p_data jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB;
BEGIN
    IF jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'row data must be a JSON object'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(v_columns) AS column_data
        INNER JOIN jsonb_object_keys(p_data) AS data_column_id
            ON data_column_id = column_data ->> 'column_id'
        WHERE column_data ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob column values must use update_blob_cell'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN v_columns;
END;
$function$;


DROP FUNCTION IF EXISTS public.add_column(uuid, character varying, text, text, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.add_column(p_workspace_id uuid, p_table_id bigint, p_name text, p_type text, p_options jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.blob_object_belongs_to_cell(text, uuid, character varying, bigint, text);

CREATE OR REPLACE FUNCTION public.blob_object_belongs_to_cell(p_object_key text, p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_column_id text)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
    SELECT p_workspace_id IN (
        SELECT public.current_user_workspaces('read')
    ) AND EXISTS (
        SELECT 1 FROM private.blob_objects
        WHERE object_key = p_object_key AND workspace_id = p_workspace_id
          AND table_id = p_table_id AND row_id = p_row_id
          AND column_id = p_column_id
    );
$function$;


DROP FUNCTION IF EXISTS public.create_row_data_index(uuid, text, text, text, text);

-- DDL half of row-data index creation, without the caller check: V70 seeds a
-- system table before any session user exists. Every other validation stays,
-- and only create_row_data_index (below) is executable by app.
CREATE OR REPLACE FUNCTION public._create_row_data_index_unchecked(p_workspace_id uuid, p_idx_name text, p_table_id bigint, p_column_id text, p_col_type text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
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
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE workspace_id = %L::UUID AND table_id = %L',
            p_idx_name, p_column_id, p_column_id, p_workspace_id, p_table_id
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
$function$;


-- Public entry point: authorise the caller, then do the DDL.
CREATE OR REPLACE FUNCTION public.create_row_data_index(p_workspace_id uuid, p_idx_name text, p_table_id bigint, p_column_id text, p_col_type text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
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

    PERFORM public._create_row_data_index_unchecked(
        p_workspace_id, p_idx_name, p_table_id, p_column_id, p_col_type
    );
END;
$function$;


DROP FUNCTION IF EXISTS public.create_table_from_template(uuid, character varying, character varying, uuid);

CREATE OR REPLACE FUNCTION public.create_table_from_template(
    p_workspace_id UUID,
    p_table_name   VARCHAR,
    p_kind         VARCHAR,
    p_by           UUID
) RETURNS BIGINT
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $function$
DECLARE
    v_table_id BIGINT;
    v_result   JSONB;
    v_columns  JSONB;
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

    SELECT jsonb_agg(
        CASE
            WHEN column_entry.column_data ->> 'type' = 'doc' THEN jsonb_set(
                jsonb_set(column_entry.column_data, '{type}', '"blob"'::JSONB),
                '{options}', coalesce(
                    column_entry.column_data -> 'options', '{}'::JSONB
                ) || '{"kind":"text"}'::JSONB
            )
            WHEN column_entry.column_data ->> 'type' = 'blob'
                 AND column_entry.column_data -> 'options' ->> 'kind' = 'doc'
            THEN jsonb_set(
                column_entry.column_data, '{options,kind}', '"text"'::JSONB
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


DROP FUNCTION IF EXISTS public.create_view(uuid, character varying, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.create_view(p_workspace_id uuid, p_table_id bigint, p_config jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.delete_column(uuid, character varying, text, uuid);

CREATE OR REPLACE FUNCTION public.delete_column(p_workspace_id uuid, p_table_id bigint, p_column_id text, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.delete_view(uuid, character varying, bigint, uuid);

CREATE OR REPLACE FUNCTION public.delete_view(p_workspace_id uuid, p_table_id bigint, p_view_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.drop_row_data_index(uuid, text, text, text);

CREATE OR REPLACE FUNCTION public.drop_row_data_index(p_workspace_id uuid, p_idx_name text, p_table_id bigint, p_column_id text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.patch_row_data(uuid, character varying, bigint, jsonb);

CREATE OR REPLACE FUNCTION public.patch_row_data(p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_patch jsonb)
 RETURNS rows
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.put_row_data(uuid, character varying, bigint, jsonb);

CREATE OR REPLACE FUNCTION public.put_row_data(p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_data jsonb)
 RETURNS rows
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.register_blob_object(uuid, character varying, bigint, text, text);

CREATE OR REPLACE FUNCTION public.register_blob_object(p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_column_id text, p_object_key text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_base TEXT;
BEGIN
    IF p_workspace_id NOT IN (
        SELECT public.current_user_workspaces('write')
    ) THEN
        RAISE EXCEPTION 'workspace write permission required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.rows AS r
        JOIN public.tables AS t USING (workspace_id, table_id)
        CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
        WHERE r.workspace_id = p_workspace_id AND r.table_id = p_table_id
          AND r.row_id = p_row_id AND c ->> 'column_id' = p_column_id
          AND c ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob cell not found'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    v_base := concat(p_workspace_id, '/', p_table_id, '/rows/',
                     p_row_id, '/blobs/', p_column_id, '/');
    IF left(p_object_key, length(v_base)) IS DISTINCT FROM v_base
       OR substring(p_object_key FROM length(v_base) + 1)
          !~ '^([.]pending/)?[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'invalid blob object key'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    INSERT INTO private.blob_objects
        (object_key, workspace_id, table_id, row_id, column_id)
    VALUES (p_object_key, p_workspace_id, p_table_id, p_row_id, p_column_id);
    INSERT INTO private.blob_cleanup_queue (object_key) VALUES (p_object_key);
END;
$function$;


DROP FUNCTION IF EXISTS public.update_blob_cell(uuid, character varying, bigint, text, jsonb);

CREATE OR REPLACE FUNCTION public.update_blob_cell(p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_column_id text, p_metadata jsonb)
 RETURNS rows
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_by      UUID;
    v_columns JSONB;
    v_row     public.rows;
BEGIN
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    IF jsonb_typeof(p_metadata) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'blob metadata must be a JSON object'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(v_columns) AS column_data
        WHERE column_data ->> 'column_id' = p_column_id
        AND   column_data ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob column not found: %', p_column_id
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE public.rows
    SET    row_data   = jsonb_set(row_data, ARRAY[p_column_id], p_metadata, TRUE),
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
$function$;


DROP FUNCTION IF EXISTS public.update_col_order(uuid, character varying, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.update_col_order(p_workspace_id uuid, p_table_id bigint, p_order jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.update_column(uuid, character varying, text, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.update_column(p_workspace_id uuid, p_table_id bigint, p_column_id text, p_patch jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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

    IF NOT public._column_names_are_unique(v_new_columns) THEN
        RAISE EXCEPTION 'duplicate normalized column name'
            USING ERRCODE = 'unique_violation';
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
$function$;


DROP FUNCTION IF EXISTS public.update_default_view(uuid, character varying, bigint, uuid);

CREATE OR REPLACE FUNCTION public.update_default_view(p_workspace_id uuid, p_table_id bigint, p_view_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_vid     BIGINT := COALESCE(p_view_id, 0);
    v_exists  BOOLEAN;
    v_new_cfg JSONB;
BEGIN
    IF v_vid != 0 THEN
        SELECT EXISTS (
            SELECT 1
            FROM   public.table_views
            WHERE  workspace_id = p_workspace_id
            AND    table_id     = p_table_id
            AND    view_id      = v_vid
        ) INTO v_exists;
        IF NOT v_exists THEN
            RAISE EXCEPTION 'view_id not found: %', v_vid;
        END IF;
    END IF;

    UPDATE public.tables
    SET    config     = jsonb_set(config, '{default_view}', to_jsonb(v_vid)),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$function$;


DROP FUNCTION IF EXISTS public.update_view(uuid, character varying, bigint, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.update_view(p_workspace_id uuid, p_table_id bigint, p_view_id bigint, p_patch jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


DROP FUNCTION IF EXISTS public.update_view_order(uuid, character varying, jsonb, uuid);

CREATE OR REPLACE FUNCTION public.update_view_order(p_workspace_id uuid, p_table_id bigint, p_order jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
$function$;


CREATE OR REPLACE FUNCTION public.get_user_sidebar()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN jsonb_build_object(
        'workspaces', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id',   workspace.workspace_id,
                    'workspace_name', workspace.workspace_name
                )
                ORDER BY workspace.workspace_name
            )
            FROM public.workspaces AS workspace
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = workspace.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB),
        'tables', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id', table_data.workspace_id,
                    'table_id',     table_data.table_id,
                    'table_name',   table_data.table_name,
                    'config',       table_data.config
                )
                ORDER BY table_data.workspace_id, table_data.table_name
            )
            FROM public.tables AS table_data
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = table_data.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB)
    );
END;
$function$;


-- ── Triggers ────────────────────────────────────────────────────────────
-- The trigger functions themselves take no table_id; they follow NEW.table_id
-- and were already bound to the renamed relations, so only the triggers move
-- to the replacement tables.

DROP TRIGGER IF EXISTS trg_tables_validate_column_names ON public.tables;
CREATE TRIGGER trg_tables_validate_column_names
BEFORE INSERT OR UPDATE OF config ON public.tables
FOR EACH ROW EXECUTE FUNCTION public.trg_validate_column_names();

DROP TRIGGER IF EXISTS trg_rows_row_id ON public.rows;
CREATE TRIGGER trg_rows_row_id
BEFORE INSERT ON public.rows
FOR EACH ROW EXECUTE FUNCTION public.trg_set_row_id_fn();

DROP TRIGGER IF EXISTS trg_rows_canonical_ts ON public.rows;
CREATE TRIGGER trg_rows_canonical_ts
BEFORE INSERT OR UPDATE OF row_data ON public.rows
FOR EACH ROW EXECUTE FUNCTION public.trg_canonical_row_data_ts_fn();

DROP TRIGGER IF EXISTS trg_rows_retire_blobs ON public.rows;
CREATE TRIGGER trg_rows_retire_blobs
BEFORE DELETE OR UPDATE OF row_data ON public.rows
FOR EACH ROW EXECUTE FUNCTION private.queue_retired_blob_objects();

DROP TRIGGER IF EXISTS trg_set_view_id ON public.table_views;
CREATE TRIGGER trg_set_view_id
BEFORE INSERT ON public.table_views
FOR EACH ROW EXECUTE FUNCTION public.trg_set_view_id_fn();



-- ── Row level security ──────────────────────────────────────────────────
-- Same shape as V52: read for members with read access of the workspace,
-- insert/update/delete for members with write access.

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['tables', 'rows', 'table_views'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_read ON public.%I', t, t);
        EXECUTE format(
            'CREATE POLICY %I_read ON public.%I
             FOR SELECT
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''read'')
                          AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_insert ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_insert ON public.%I
             FOR INSERT
             WITH CHECK (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'')
                          AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_update ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_update ON public.%I
             FOR UPDATE
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'')
                          AS allowed(workspace_id)
                 )
             )
             WITH CHECK (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'')
                          AS allowed(workspace_id)
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_delete ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_delete ON public.%I
             FOR DELETE
             USING (
                 workspace_id IN (
                     SELECT allowed.workspace_id
                     FROM public.current_user_workspaces(''write'')
                          AS allowed(workspace_id)
                 )
             )', t, t
        );
    END LOOP;
END $$;

ALTER TABLE public.tables      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rows        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.table_views ENABLE ROW LEVEL SECURITY;



-- ── Table and function grants ───────────────────────────────────────────
-- V15 gave app/mgr DML on the relations that existed then; the replacements
-- are new relations, so the same grants are re-issued here.

GRANT SELECT, INSERT, UPDATE, DELETE ON public.tables      TO app, mgr;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.rows        TO app, mgr;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.table_views TO app, mgr;

REVOKE ALL ON FUNCTION public.get_user_sidebar() FROM public;
GRANT EXECUTE ON FUNCTION public.get_user_sidebar() TO app, mgr;

-- Dropping the old signatures dropped their grants with them.
GRANT EXECUTE ON
    FUNCTION public._build_rd_idx_name(uuid, bigint, text) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public._seed_blank(uuid, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public._seed_crm(uuid, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public._seed_pm(uuid, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public._seed_workflow(uuid, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public._validate_row_data_mutation(uuid, bigint, jsonb) TO app;

GRANT EXECUTE ON
    FUNCTION public.add_column(uuid, bigint, text, text, jsonb, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.blob_object_belongs_to_cell(text, uuid, bigint, bigint, text) TO app;

GRANT EXECUTE ON
    FUNCTION public.create_row_data_index(uuid, text, bigint, text, text) TO app;

-- Internal DDL helper: migrations only, never app.
REVOKE ALL ON
    FUNCTION public._create_row_data_index_unchecked(uuid, text, bigint, text, text)
    FROM public;

GRANT EXECUTE ON
    FUNCTION public.create_table_from_template(uuid, character varying, character varying, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.create_view(uuid, bigint, jsonb, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.delete_column(uuid, bigint, text, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.delete_view(uuid, bigint, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.drop_row_data_index(uuid, text, bigint, text) TO app;

GRANT EXECUTE ON
    FUNCTION public.patch_row_data(uuid, bigint, bigint, jsonb) TO app;

GRANT EXECUTE ON
    FUNCTION public.put_row_data(uuid, bigint, bigint, jsonb) TO app;

GRANT EXECUTE ON
    FUNCTION public.register_blob_object(uuid, bigint, bigint, text, text) TO app;

GRANT EXECUTE ON
    FUNCTION public.update_blob_cell(uuid, bigint, bigint, text, jsonb) TO app;

GRANT EXECUTE ON
    FUNCTION public.update_col_order(uuid, bigint, jsonb, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.update_column(uuid, bigint, text, jsonb, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.update_default_view(uuid, bigint, bigint, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.update_view(uuid, bigint, bigint, jsonb, uuid) TO app, mgr;

GRANT EXECUTE ON
    FUNCTION public.update_view_order(uuid, bigint, jsonb, uuid) TO app, mgr;
