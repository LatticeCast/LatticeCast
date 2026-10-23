-- upgrade
-- Table-scoped child storage: the workspace lives on the table, once.
--
-- V68 hung a workspace_id on rows and table_views (and on the two private
-- children) so RLS could authorise on it, and accepted the trade-off that a
-- single-column foreign key no longer proves child and table agree. That
-- trade-off is a hole: a row could be stored under workspace A while its
-- table belonged to B, and RLS would authorise the row against A, the
-- workspace the caller never had a claim on.
--
-- This migration closes it by removing the copy. Children are keyed and
-- authorised by table_id, which is globally unique and foreign-keyed to the
-- table that owns the workspace. The policies first resolve the caller's
-- legal table ids from the workspace grants, then compare against table_id,
-- so the authority for a row is the table row itself, not a value the child
-- carries. The workspace-wide child indexes go with the columns they served;
-- the table-scoped primary keys already cover every remaining lookup.

DROP POLICY IF EXISTS rows_read         ON public.rows;
DROP POLICY IF EXISTS rows_write_insert ON public.rows;
DROP POLICY IF EXISTS rows_write_update ON public.rows;
DROP POLICY IF EXISTS rows_write_delete ON public.rows;
DROP POLICY IF EXISTS table_views_read         ON public.table_views;
DROP POLICY IF EXISTS table_views_write_insert ON public.table_views;
DROP POLICY IF EXISTS table_views_write_update ON public.table_views;
DROP POLICY IF EXISTS table_views_write_delete ON public.table_views;

-- Dropping the column drops the workspace-wide index V68 added for the old
-- predicates; rows_pkey (table_id, row_id) and table_views_pkey
-- (table_id, view_id) are the lookups the application actually makes.
ALTER TABLE public.rows        DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE public.table_views DROP COLUMN IF EXISTS workspace_id;

-- The row-id counter is per table, exactly like the rows it numbers.
ALTER TABLE private.table_row_counters
    DROP CONSTRAINT IF EXISTS table_row_counters_pkey;
ALTER TABLE private.table_row_counters DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE private.table_row_counters
    ADD CONSTRAINT table_row_counters_pkey PRIMARY KEY (table_id);

-- Ownership of a blob object is (table, row, column); the workspace is the
-- parent table's, and blob_object_belongs_to_cell resolves it there.
ALTER TABLE private.blob_objects DROP COLUMN IF EXISTS workspace_id;


-- ── Helpers ─────────────────────────────────────────────────────────────────

-- Callers still address a child through its workspace (that is how the API
-- scopes a request), so the workspace/table pair stays a checked claim rather
-- than a filter that silently matches nothing.
CREATE OR REPLACE FUNCTION public._require_table_in_workspace(p_workspace_id uuid, p_table_id bigint)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   public.tables
        WHERE  table_id     = p_table_id
        AND    workspace_id = p_workspace_id
    ) THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;
END;
$function$;

REVOKE ALL    ON FUNCTION public._require_table_in_workspace(uuid, bigint) FROM public;
GRANT EXECUTE ON FUNCTION public._require_table_in_workspace(uuid, bigint) TO app, mgr;

-- The caller's legal table ids, resolved once per statement. SECURITY DEFINER
-- because public.tables is itself RLS-protected: a policy on rows must not
-- depend on the RLS view of the table it is authorising against.
CREATE OR REPLACE FUNCTION public.current_user_tables(p_action character varying)
 RETURNS SETOF bigint
 LANGUAGE sql
 STABLE PARALLEL SAFE SECURITY DEFINER ROWS 32
 SET search_path TO 'public', 'pg_temp'
AS $function$
    SELECT table_data.table_id
    FROM   public.tables AS table_data
    WHERE  table_data.workspace_id IN (
               SELECT public.current_user_workspaces(p_action)
           );
$function$;

REVOKE ALL    ON FUNCTION public.current_user_tables(character varying) FROM public;
GRANT EXECUTE ON FUNCTION public.current_user_tables(character varying) TO app, mgr;


-- ── Workspace-keyed child functions ─────────────────────────────────────────
-- Same signatures; the workspace stays the caller's claim and is checked
-- against the table, while the child rows are addressed by table_id alone.
CREATE OR REPLACE FUNCTION private.queue_retired_blob_objects()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_data JSONB;
BEGIN
    v_data := CASE WHEN TG_OP = 'DELETE' THEN '{}'::JSONB ELSE NEW.row_data END;
    INSERT INTO private.blob_cleanup_queue (object_key)
    SELECT obj.object_key
    FROM private.blob_objects AS obj
    JOIN LATERAL jsonb_each(OLD.row_data) AS cell
      ON cell.value ->> 'key' = obj.object_key
    WHERE obj.table_id = OLD.table_id
      AND obj.row_id = OLD.row_id AND obj.column_id = cell.key
      AND (v_data -> cell.key ->> 'key') IS DISTINCT FROM obj.object_key
    ON CONFLICT (object_key) DO NOTHING;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;


CREATE OR REPLACE FUNCTION public.trg_set_view_id_fn()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.view_id IS NULL OR NEW.view_id = 0 THEN
        SELECT COALESCE(MAX(view_id), 0) + 1
        INTO   NEW.view_id
        FROM   public.table_views
        WHERE  table_id = NEW.table_id;
    END IF;
    RETURN NEW;
END;
$function$;


CREATE OR REPLACE FUNCTION public.trg_set_row_id_fn()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'private', 'public', 'pg_temp'
AS $function$
BEGIN
    IF NEW.row_id IS NULL OR NEW.row_id = 0 THEN
        INSERT INTO private.table_row_counters
            (table_id, last_row_id)
        VALUES (NEW.table_id, 1)
        ON CONFLICT (table_id) DO UPDATE
        SET last_row_id = private.table_row_counters.last_row_id + 1
        RETURNING last_row_id INTO NEW.row_id;
    ELSE
        -- An explicitly supplied row_id must still advance the
        -- high-water mark, or the counter stays behind and a later
        -- auto-allocation walks straight into the existing row's key.
        -- RowRepository.create() never supplies one, but V36 seeds rows
        -- directly and mgr tooling can too. GREATEST() so an explicit
        -- id lower than the mark cannot rewind it; a duplicate is still
        -- rejected by the rows primary key, which is the correct owner
        -- of that error.
        INSERT INTO private.table_row_counters
            (table_id, last_row_id)
        VALUES (NEW.table_id, NEW.row_id)
        ON CONFLICT (table_id) DO UPDATE
        SET last_row_id = greatest(
                private.table_row_counters.last_row_id,
                excluded.last_row_id
            );
    END IF;
    RETURN NEW;
END;
$function$;


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


CREATE OR REPLACE FUNCTION public.trg_canonical_row_data_ts_fn()
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

    NEW.row_data := public._normalize_row_data_timestamps(
        v_columns, NEW.row_data
    );

    RETURN NEW;
END;
$function$;


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
    p_data := public._normalize_row_data_timestamps(v_columns, p_data);
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


CREATE OR REPLACE FUNCTION public.blob_object_belongs_to_cell(p_object_key text, p_workspace_id uuid, p_table_id bigint, p_row_id bigint, p_column_id text)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
    SELECT p_workspace_id IN (
        SELECT public.current_user_workspaces('read')
    ) AND EXISTS (
        SELECT 1
        FROM   private.blob_objects AS owned
        JOIN   public.tables AS parent
               ON parent.table_id = owned.table_id
        WHERE  owned.object_key = p_object_key
        AND    owned.table_id   = p_table_id
        AND    owned.row_id     = p_row_id
        AND    owned.column_id  = p_column_id
        AND    parent.workspace_id = p_workspace_id
    );
$function$;


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
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    ELSIF p_col_type IN ('date', 'datetime') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((CASE WHEN (row_data ->> %L) ~ ''^-?[0-9]+$'' '
            'THEN (row_data ->> %L)::BIGINT ELSE NULL END)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_column_id, p_table_id
        );
    ELSIF p_col_type IN ('text', 'string', 'select', 'email', 'url', 'phone') THEN
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING btree ((row_data ->> %L)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    ELSE
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.rows '
            'USING gin ((row_data -> %L)) '
            'WHERE table_id = %L',
            p_idx_name, p_column_id, p_table_id
        );
    END IF;
END;
$function$;


CREATE OR REPLACE FUNCTION public.create_view(p_workspace_id uuid, p_table_id bigint, p_config jsonb, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_view_id BIGINT;
    v_new_cfg JSONB;
BEGIN
    PERFORM public._require_table_in_workspace(
        p_workspace_id, p_table_id
    );

    INSERT INTO public.table_views (
        table_id, config,
        created_by, updated_by
    ) VALUES (
        p_table_id, p_config, p_by, p_by
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
    PERFORM public._require_table_in_workspace(
        p_workspace_id, p_table_id
    );

    DELETE FROM public.table_views
    WHERE  table_id = p_table_id
    AND    view_id  = p_view_id;

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
        JOIN public.tables AS t ON t.table_id = r.table_id
        CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
        WHERE t.workspace_id = p_workspace_id AND r.table_id = p_table_id
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
        (object_key, table_id, row_id, column_id)
    VALUES (p_object_key, p_table_id, p_row_id, p_column_id);
    INSERT INTO private.blob_cleanup_queue (object_key) VALUES (p_object_key);
END;
$function$;


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
    PERFORM public._require_table_in_workspace(
        p_workspace_id, p_table_id
    );

    IF v_vid != 0 THEN
        SELECT EXISTS (
            SELECT 1
            FROM   public.table_views
            WHERE  table_id = p_table_id
            AND    view_id  = v_vid
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
    PERFORM public._require_table_in_workspace(
        p_workspace_id, p_table_id
    );

    SELECT config INTO v_merged
    FROM   public.table_views
    WHERE  table_id = p_table_id
    AND    view_id  = p_view_id
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
    WHERE  table_id = p_table_id
    AND    view_id  = p_view_id;

    SELECT config
    INTO   v_new_cfg
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    RETURN v_new_cfg;
END;
$function$;


-- ── Row level security ──────────────────────────────────────────────────────
-- Read for members with read access, insert/update/delete for members with
-- write access. Membership names workspaces; the legal table ids are derived
-- from those workspaces, and the child row compares against them.

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['rows', 'table_views'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_read ON public.%I', t, t);
        EXECUTE format(
            'CREATE POLICY %I_read ON public.%I
             FOR SELECT
             USING (
                 table_id IN (
                     SELECT allowed.table_id
                     FROM public.current_user_tables(''read'')
                          AS allowed(table_id)
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
                 table_id IN (
                     SELECT allowed.table_id
                     FROM public.current_user_tables(''write'')
                          AS allowed(table_id)
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
                 table_id IN (
                     SELECT allowed.table_id
                     FROM public.current_user_tables(''write'')
                          AS allowed(table_id)
                 )
             )
             WITH CHECK (
                 table_id IN (
                     SELECT allowed.table_id
                     FROM public.current_user_tables(''write'')
                          AS allowed(table_id)
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
                 table_id IN (
                     SELECT allowed.table_id
                     FROM public.current_user_tables(''write'')
                          AS allowed(table_id)
                 )
             )', t, t
        );
    END LOOP;
END $$;

ALTER TABLE public.rows        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.table_views ENABLE ROW LEVEL SECURITY;


-- ── Per-column row indexes ──────────────────────────────────────────────────
-- Their predicates were workspace_keyed, so dropping the column dropped
-- them. They are derived state (see _create_row_data_index_unchecked), so
-- rebuilding every existing one here is the cheap, correct repair.

DO $$
DECLARE
    entry RECORD;
BEGIN
    FOR entry IN
        SELECT
            table_data.workspace_id,
            table_data.table_id,
            column_data ->> 'column_id' AS column_id,
            column_data ->> 'type'      AS column_type
        FROM public.tables AS table_data
        CROSS JOIN LATERAL jsonb_array_elements(
            table_data.config -> 'columns'
        ) AS column_data
        WHERE column_data ->> 'type' IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        )
    LOOP
        PERFORM public._create_row_data_index_unchecked(
            entry.workspace_id,
            public._build_rd_idx_name(
                entry.workspace_id, entry.table_id, entry.column_id
            ),
            entry.table_id,
            entry.column_id,
            entry.column_type
        );
    END LOOP;
END;
$$;
