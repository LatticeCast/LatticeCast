-- Column types are storage types only: text, int, double, strings, blob.
--
-- How a column is read (a date, a link, a checkbox, a select) is the client's
-- business. It is carried in the column's config as options.display, next to
-- options.note, and the database never interprets it. So the types that only
-- described a reading (string, url, select, checkbox, date, datetime, number)
-- can no longer be created.
--
-- strings is an array of strings; a client reads it as tags or as a checkbox
-- (T, F). int is a BIGINT. A per-column index can be made for text (btree),
-- int (btree) and strings (GIN); double and blob are never indexed.
--
-- This migration changes functions only. It converts no existing column and
-- no stored value: what an old column becomes depends on its data and its
-- meaning, so that is decided column by column with convert_column_type.py.

CREATE OR REPLACE FUNCTION public._column_types_are_storage(p_columns JSONB)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'public', 'pg_temp'
AS $function$
    SELECT NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(coalesce(p_columns, '[]'::JSONB)) AS column_data
        WHERE coalesce(column_data ->> 'type', '') NOT IN ('text', 'int', 'double', 'strings', 'blob')
    );
$function$;

REVOKE ALL    ON FUNCTION public._column_types_are_storage(JSONB) FROM public;
GRANT EXECUTE ON FUNCTION public._column_types_are_storage(JSONB) TO app, mgr;

-- An int cell is a BIGINT or null. An integral number such as 3.0 is stored
-- as 3 and an empty string as null; anything else is refused, so an int
-- column can always be indexed and compared as an integer.
CREATE OR REPLACE FUNCTION public._coerce_row_data_ints(p_columns JSONB, p_data JSONB)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_column JSONB;
    v_id     TEXT;
    v_value  JSONB;
    v_number NUMERIC;
BEGIN
    FOR v_column IN
        SELECT column_data
        FROM jsonb_array_elements(p_columns) AS column_data
        WHERE column_data ->> 'type' = 'int'
          AND p_data ? (column_data ->> 'column_id')
    LOOP
        v_id    := v_column ->> 'column_id';
        v_value := p_data -> v_id;

        IF jsonb_typeof(v_value) = 'null' THEN
            CONTINUE;
        END IF;
        IF jsonb_typeof(v_value) = 'string' AND btrim(v_value #>> '{}') = '' THEN
            p_data := jsonb_set(p_data, ARRAY[v_id], 'null'::JSONB);
            CONTINUE;
        END IF;
        IF jsonb_typeof(v_value) = 'number' THEN
            v_number := (v_value #>> '{}')::NUMERIC;
            IF v_number % 1 = 0
               AND v_number BETWEEN -9223372036854775808 AND 9223372036854775807 THEN
                p_data := jsonb_set(p_data, ARRAY[v_id], to_jsonb(v_number::BIGINT));
                CONTINUE;
            END IF;
        END IF;

        RAISE EXCEPTION 'int column "%" takes an integer or null, got %',
            v_column ->> 'name', v_value
            USING ERRCODE = 'invalid_parameter_value';
    END LOOP;

    RETURN p_data;
END;
$function$;

REVOKE ALL    ON FUNCTION public._coerce_row_data_ints(JSONB, JSONB) FROM public;
GRANT EXECUTE ON FUNCTION public._coerce_row_data_ints(JSONB, JSONB) TO app, mgr;

-- The date/datetime normaliser goes with the types it served.
DROP TRIGGER IF EXISTS trg_rows_canonical_ts ON public.rows;

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
    p_patch := public._coerce_row_data_ints(v_columns, p_patch);
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    UPDATE public.rows
    SET    row_data   = row_data || p_patch,
           updated_by = v_by,
           updated_at = now()
    WHERE  table_id = p_table_id
    AND    row_id   = p_row_id
    RETURNING * INTO v_row;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'row not found: %, %, %',
            p_workspace_id, p_table_id, p_row_id;
    END IF;

    RETURN v_row;
END;
$function$;

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
    p_data := public._coerce_row_data_ints(v_columns, p_data);
    v_by := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;

    SELECT *
    INTO   v_current
    FROM   public.rows
    WHERE  table_id = p_table_id
    AND    row_id   = p_row_id
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
    WHERE  table_id = p_table_id
    AND    row_id   = p_row_id
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$function$;

DROP FUNCTION IF EXISTS public.trg_canonical_row_data_ts_fn();
DROP FUNCTION IF EXISTS public._normalize_row_data_timestamps(jsonb, jsonb);
DROP FUNCTION IF EXISTS public.to_canonical_epoch_ms(jsonb, text);
DROP FUNCTION IF EXISTS public._parse_legacy_ts_ms(text);

-- A per-column index: btree for text and int, GIN for strings. Never double or blob.
CREATE OR REPLACE FUNCTION public._create_row_data_index_unchecked(
    p_workspace_id UUID,
    p_idx_name    TEXT,
    p_table_id    BIGINT,
    p_column_id   TEXT,
    p_col_type    TEXT
) RETURNS VOID
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
    IF p_col_type NOT IN ('text', 'int', 'strings') THEN
        RAISE EXCEPTION 'only text, int and strings columns take a per-column index, got %', p_col_type
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.tables AS table_data
        CROSS JOIN LATERAL jsonb_array_elements(
            table_data.config -> 'columns'
        ) AS column_data
        WHERE table_data.workspace_id = p_workspace_id
          AND table_data.table_id = p_table_id
          AND column_data ->> 'column_id' = p_column_id
          AND column_data ->> 'type' = p_col_type
    ) THEN
        RAISE EXCEPTION 'indexed column not found: %', p_column_id
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_col_type = 'int' THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_column_id, p_table_id
        );
    ELSIF p_col_type = 'text' THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((row_data ->> %L)) WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    ELSE
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING gin ((row_data -> %L)) WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.add_column(p_workspace_id uuid, p_table_id bigint, p_name text, p_type text, p_options jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB;
    v_new_col JSONB;
    v_new_cfg JSONB;
BEGIN
    SELECT config -> 'columns' INTO v_columns
    FROM public.tables WHERE workspace_id = p_workspace_id AND table_id = p_table_id;
    IF v_columns IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    v_new_col := _build_column_dict(p_name, p_type, p_options);
    IF NOT public._column_types_are_storage(jsonb_build_array(v_new_col)) THEN
        RAISE EXCEPTION 'unknown column type: % (text, int, double, strings, blob)', p_type
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT public._column_names_are_unique(v_columns || v_new_col) THEN
        RAISE EXCEPTION 'duplicate normalized column name' USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE public.tables
    SET config = jsonb_set(config, '{columns}', coalesce(config -> 'columns', '[]'::JSONB) || v_new_col),
        updated_by = p_by, updated_at = now()
    WHERE workspace_id = p_workspace_id AND table_id = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$function$;

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

    -- Only the patched column: a table may still hold columns not yet converted.
    IF p_patch ? 'type'
       AND NOT public._column_types_are_storage(jsonb_build_array(jsonb_build_object('type', p_patch ->> 'type'))) THEN
        RAISE EXCEPTION 'unknown column type: % (text, int, double, strings, blob)', p_patch ->> 'type'
            USING ERRCODE = 'invalid_parameter_value';
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

-- Templates seed storage types and say how each column reads.
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
        _build_column_dict('Stage',       'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"lead","color":"#9ca3af"},
                {"value":"qualified","color":"#60a5fa"},
                {"value":"proposal","color":"#facc15"},
                {"value":"won","color":"#4ade80"},
                {"value":"lost","color":"#f87171"}
            ]}'::JSONB),
        _build_column_dict('Value',       'double', '{}'::JSONB),
        _build_column_dict('Owner',       'text',   '{}'::JSONB),
        _build_column_dict('Close Date',  'int',    '{"display":"date"}'::JSONB),
        _build_column_dict('Tags',        'strings', '{}'::JSONB),
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
$function$

;

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
        _build_column_dict('Type',        'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"epic","color":"#a78bfa"},
                {"value":"story","color":"#60a5fa"},
                {"value":"task","color":"#4ade80"},
                {"value":"bug","color":"#f87171"}
            ]}'::JSONB),
        _build_column_dict('Status',      'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"todo","color":"#9ca3af"},
                {"value":"in_progress","color":"#60a5fa"},
                {"value":"testing","color":"#a78bfa"},
                {"value":"debugging","color":"#f87171"},
                {"value":"review","color":"#facc15"},
                {"value":"done","color":"#4ade80"},
                {"value":"merged","color":"#34d399"}
            ]}'::JSONB),
        _build_column_dict('Priority',    'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"critical","color":"#ef4444"},
                {"value":"high","color":"#f97316"},
                {"value":"medium","color":"#facc15"},
                {"value":"low","color":"#9ca3af"}
            ]}'::JSONB),
        _build_column_dict('Assignee',    'text',   '{}'::JSONB),
        _build_column_dict('Start Date',  'int',    '{"display":"date"}'::JSONB),
        _build_column_dict('Due Date',    'int',    '{"display":"date"}'::JSONB),
        _build_column_dict('Estimate',    'int',    '{}'::JSONB),
        _build_column_dict('Tags',        'strings', '{}'::JSONB),
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
$function$

;

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
        _build_column_dict('type',        'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"START","color":"#15a74b"},
                {"value":"STEP","color":"#246ac0"},
                {"value":"TOOL","color":"#dbb726"},
                {"value":"CONDITION","color":"#744de7"},
                {"value":"INFO","color":"#9ca3af"},
                {"value":"SUBGRAPH","color":"#f97316"}
            ]}'::JSONB),
        _build_column_dict('description', 'text',   '{}'::JSONB),
        _build_column_dict('graph_name',  'text',   '{"display":"select"}'::JSONB ||
            '{"choices":[
                {"value":"root","color":"#9ca3af"}
            ]}'::JSONB),
        _build_column_dict('nexts',       'text',   '[]'::JSONB),
        _build_column_dict('true_next',   'text',   '{}'::JSONB),
        _build_column_dict('false_next',  'text',   '{}'::JSONB),
        _build_column_dict('pos_x',       'double', '{}'::JSONB),
        _build_column_dict('pos_y',       'double', '{}'::JSONB)
    );
    v_col_ids := _columns_name_map(v_columns);

    -- Workflow view (default)
    INSERT INTO public.table_views (
        table_id, config, created_by, updated_by
    ) VALUES (
        p_table_id,
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
$function$

;



-- Every write path coerces int cells, including a raw INSERT or UPDATE.
CREATE OR REPLACE FUNCTION public.trg_coerce_row_data_ints_fn()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB;
BEGIN
    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  table_id = NEW.table_id;

    IF v_columns IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.row_data := public._coerce_row_data_ints(v_columns, NEW.row_data);

    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.trg_coerce_row_data_ints_fn() FROM public;

DROP TRIGGER IF EXISTS trg_rows_coerce_ints ON public.rows;
CREATE TRIGGER trg_rows_coerce_ints
    BEFORE INSERT OR UPDATE OF row_data ON public.rows
    FOR EACH ROW EXECUTE FUNCTION public.trg_coerce_row_data_ints_fn();

