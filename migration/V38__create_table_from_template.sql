-- upgrade
-- V38: Atomic table creation via a single PG function.
--
-- Replaces the multi-step Python orchestration that creates a table +
-- populates __schema__ + creates per-column indexes + (for templates)
-- seeds views. Each step used to be a separate transaction; a failure
-- mid-stream left orphan rows or a table with an empty schema. The new
-- function is one transaction — all or nothing.
--
-- Signature:
--   create_table_from_template(workspace_id, table_id, kind, created_by)
--     returns public.tables%ROWTYPE
--   kind in ('blank','pm','crm')
--
-- Not SECURITY DEFINER: the caller's RLS context governs INSERTs into
-- public.tables / public.table_views (workspace membership check).
-- Per-column index creation calls create_row_data_index (which IS
-- SECURITY DEFINER) — no DDL privileges leak.

-- ── Helper: idx name builder (mirrors backend/src/repository/table.py) ──
CREATE OR REPLACE FUNCTION _BUILD_RD_IDX_NAME(p_table_id TEXT, p_column_id TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_clean_tid TEXT;
    v_clean_cid TEXT;
BEGIN
    -- Strip hyphens and check for ASCII-only [A-Za-z0-9_].
    -- Fall back to md5 hash for non-ASCII / special-char names so the
    -- regex check inside create_row_data_index passes.
    v_clean_tid := REPLACE(p_table_id, '-', '');
    IF v_clean_tid <> '' AND v_clean_tid ~ '^[A-Za-z0-9_]+$' THEN
        v_clean_tid := SUBSTRING(v_clean_tid, 1, 12);
    ELSE
        v_clean_tid := SUBSTRING(MD5(p_table_id), 1, 12);
    END IF;
    v_clean_cid := SUBSTRING(REPLACE(p_column_id, '-', ''), 1, 12);
    RETURN 'idx_rd_' || v_clean_tid || '_' || v_clean_cid;
END;
$$;

GRANT EXECUTE ON FUNCTION _BUILD_RD_IDX_NAME(TEXT, TEXT) TO app;

-- ── Helper: build the column array (with fresh UUIDs) for each template ──
-- Returns a JSONB array of column dicts. The position is the array index.
CREATE OR REPLACE FUNCTION _BUILD_TEMPLATE_COLUMNS(p_kind TEXT)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_specs JSONB;
    v_result JSONB := '[]'::JSONB;
    v_spec JSONB;
    v_pos INT := 0;
BEGIN
    -- Column specs per template, in display order.
    IF p_kind = 'blank' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Description","type":"text","options":{}}
        ]'::JSONB;
    ELSIF p_kind = 'pm' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Type","type":"select","options":{"choices":[
                {"value":"epic","color":"bg-purple-100 text-purple-700"},
                {"value":"story","color":"bg-blue-100 text-blue-700"},
                {"value":"task","color":"bg-green-100 text-green-700"},
                {"value":"bug","color":"bg-red-100 text-red-700"}
            ]}},
            {"name":"Status","type":"select","options":{"choices":[
                {"value":"todo","color":"bg-gray-100 text-gray-700"},
                {"value":"in_progress","color":"bg-blue-100 text-blue-700"},
                {"value":"testing","color":"bg-purple-100 text-purple-700"},
                {"value":"debugging","color":"bg-red-100 text-red-700"},
                {"value":"review","color":"bg-yellow-100 text-yellow-700"},
                {"value":"done","color":"bg-green-100 text-green-700"},
                {"value":"merged","color":"bg-emerald-100 text-emerald-700"}
            ]}},
            {"name":"Priority","type":"select","options":{"choices":[
                {"value":"critical","color":"bg-red-100 text-red-700"},
                {"value":"high","color":"bg-orange-100 text-orange-700"},
                {"value":"medium","color":"bg-yellow-100 text-yellow-700"},
                {"value":"low","color":"bg-gray-100 text-gray-700"}
            ]}},
            {"name":"Assignee","type":"text","options":{}},
            {"name":"Start Date","type":"date","options":{}},
            {"name":"Due Date","type":"date","options":{}},
            {"name":"Estimate","type":"number","options":{}},
            {"name":"Tags","type":"tags","options":{}},
            {"name":"Description","type":"text","options":{}},
            {"name":"Parent","type":"text","options":{}}
        ]'::JSONB;
    ELSIF p_kind = 'crm' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Stage","type":"select","options":{"choices":[
                {"value":"lead","color":"bg-gray-100 text-gray-700"},
                {"value":"qualified","color":"bg-blue-100 text-blue-700"},
                {"value":"proposal","color":"bg-yellow-100 text-yellow-700"},
                {"value":"won","color":"bg-green-100 text-green-700"},
                {"value":"lost","color":"bg-red-100 text-red-700"}
            ]}},
            {"name":"Value","type":"number","options":{}},
            {"name":"Owner","type":"text","options":{}},
            {"name":"Close Date","type":"date","options":{}},
            {"name":"Tags","type":"tags","options":{}},
            {"name":"Description","type":"text","options":{}}
        ]'::JSONB;
    ELSE
        RAISE EXCEPTION 'Unknown template kind: %', p_kind;
    END IF;

    -- Stamp each spec with a fresh UUID column_id + position.
    FOR v_spec IN SELECT * FROM JSONB_ARRAY_ELEMENTS(v_specs) LOOP
        v_result := v_result || JSONB_BUILD_ARRAY(
            JSONB_BUILD_OBJECT(
                'column_id', GEN_RANDOM_UUID()::TEXT,
                'name',      v_spec->>'name',
                'type',      v_spec->>'type',
                'options',   COALESCE(v_spec->'options', '{}'::JSONB),
                'position',  v_pos,
                'created_at', NOW()
            )
        );
        v_pos := v_pos + 1;
    END LOOP;

    RETURN v_result;
END;
$$;

GRANT EXECUTE ON FUNCTION _BUILD_TEMPLATE_COLUMNS(TEXT) TO app;

-- ── Helper: name → column_id map from a columns array ──
CREATE OR REPLACE FUNCTION _COLUMNS_NAME_MAP(p_columns JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
    SELECT JSONB_OBJECT_AGG(c->>'name', c->>'column_id')
    FROM JSONB_ARRAY_ELEMENTS(p_columns) AS c;
$$;

GRANT EXECUTE ON FUNCTION _COLUMNS_NAME_MAP(JSONB) TO app;

-- ── Main function: create + populate a table atomically ─────────────────
CREATE OR REPLACE FUNCTION CREATE_TABLE_FROM_TEMPLATE(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_kind VARCHAR,
    p_created_by UUID
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_columns JSONB;
    v_col_ids JSONB;
    v_col JSONB;
    v_col_type TEXT;
    v_col_id TEXT;
    v_idx_name TEXT;
    v_default_view_name TEXT := NULL;
BEGIN
    IF p_kind NOT IN ('blank', 'pm', 'crm') THEN
        RAISE EXCEPTION 'Unknown template kind: %', p_kind;
    END IF;

    -- 1. Insert the tables row. The AFTER-INSERT trigger
    --    trg_tables_create_schema_and_order creates the __schema__ +
    --    __order__ rows (empty configs).
    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    -- 2. Build the template's columns and the name→column_id map.
    v_columns := _BUILD_TEMPLATE_COLUMNS(p_kind);
    v_col_ids := _COLUMNS_NAME_MAP(v_columns);

    -- 3. Replace the empty __schema__ config with the real columns.
    UPDATE public.table_views
    SET config = v_columns,
        updated_by = p_created_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    -- 4. Per-column GIN/B-tree indexes. Skipped types (e.g. 'doc') are
    --    a no-op inside create_row_data_index.
    FOR v_col IN SELECT * FROM JSONB_ARRAY_ELEMENTS(v_columns) LOOP
        v_col_id := v_col->>'column_id';
        v_col_type := v_col->>'type';
        IF v_col_type IN ('number','date','select','tags','text','checkbox') THEN
            v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, v_col_id);
            PERFORM CREATE_ROW_DATA_INDEX(
                v_idx_name, p_table_id::TEXT, v_col_id, v_col_type
            );
        END IF;
    END LOOP;

    -- 5. Template-specific views.
    IF p_kind = 'pm' THEN
        INSERT INTO public.table_views (
            workspace_id, table_id, name, type, config, created_by, updated_by
        ) VALUES
        (p_workspace_id, p_table_id, 'Sprint Board', 'kanban',
         JSONB_BUILD_OBJECT(
            'group_by', v_col_ids->>'Status',
            'card_fields', JSONB_BUILD_ARRAY(
                v_col_ids->>'Title',
                v_col_ids->>'Priority',
                v_col_ids->>'Assignee'
            )
         ),
         p_created_by, p_created_by),
        (p_workspace_id, p_table_id, 'Roadmap', 'timeline',
         JSONB_BUILD_OBJECT(
            'start_col', v_col_ids->>'Start Date',
            'end_col',   v_col_ids->>'Due Date',
            'color_by',  v_col_ids->>'Status',
            'group_by',  v_col_ids->>'Type'
         ),
         p_created_by, p_created_by);

        UPDATE public.table_views
        SET config = '["Sprint Board","Roadmap"]'::JSONB,
            updated_by = p_created_by, updated_at = NOW()
        WHERE workspace_id = p_workspace_id
          AND table_id = p_table_id
          AND name = '__order__';

        v_default_view_name := 'Sprint Board';

    ELSIF p_kind = 'crm' THEN
        INSERT INTO public.table_views (
            workspace_id, table_id, name, type, config, created_by, updated_by
        ) VALUES
        (p_workspace_id, p_table_id, 'Pipeline', 'kanban',
         JSONB_BUILD_OBJECT(
            'group_by', v_col_ids->>'Stage',
            'card_fields', JSONB_BUILD_ARRAY(
                v_col_ids->>'Title',
                v_col_ids->>'Value',
                v_col_ids->>'Owner'
            )
         ),
         p_created_by, p_created_by),
        (p_workspace_id, p_table_id, 'Sales Dashboard', 'dashboard',
         JSONB_BUILD_OBJECT(
            'layout', JSONB_BUILD_ARRAY(
                JSONB_BUILD_OBJECT('id','pipeline_value','x',0,'y',0,'w',3,'h',2),
                JSONB_BUILD_OBJECT('id','by_stage','x',3,'y',0,'w',6,'h',4),
                JSONB_BUILD_OBJECT('id','by_owner','x',9,'y',0,'w',3,'h',4),
                JSONB_BUILD_OBJECT('id','won_value','x',0,'y',2,'w',3,'h',2),
                JSONB_BUILD_OBJECT('id','recent','x',0,'y',4,'w',12,'h',4)
            ),
            'blocks', JSONB_BUILD_OBJECT(
                'pipeline_value', JSONB_BUILD_OBJECT(
                    'kind','number','title','Pipeline Value',
                    'lql', FORMAT(
                        'table(%L) | filter((r)->{r.stage in @["lead","qualified","proposal"]}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'field','value','format','$,.0f'
                ),
                'by_stage', JSONB_BUILD_OBJECT(
                    'kind','chart','title','Value by Stage',
                    'lql', FORMAT(
                        'table(%L) | group_by((r)->{r.stage}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'echarts', JSONB_BUILD_OBJECT(
                        'dataset', JSONB_BUILD_ARRAY(JSONB_BUILD_OBJECT('$inject','rows')),
                        'xAxis', JSONB_BUILD_OBJECT('type','category'),
                        'yAxis', JSONB_BUILD_OBJECT('type','value'),
                        'series', JSONB_BUILD_ARRAY(JSONB_BUILD_OBJECT(
                            'type','bar',
                            'encode', JSONB_BUILD_OBJECT('x','dim_0','y','value')
                        ))
                    )
                ),
                'by_owner', JSONB_BUILD_OBJECT(
                    'kind','chart','title','Deals by Owner',
                    'lql', FORMAT(
                        'table(%L) | group_by((r)->{r.owner}) | aggregate(count())',
                        p_table_id
                    ),
                    'echarts', JSONB_BUILD_OBJECT(
                        'dataset', JSONB_BUILD_ARRAY(JSONB_BUILD_OBJECT('$inject','rows')),
                        'xAxis', JSONB_BUILD_OBJECT('type','category'),
                        'yAxis', JSONB_BUILD_OBJECT('type','value'),
                        'series', JSONB_BUILD_ARRAY(JSONB_BUILD_OBJECT(
                            'type','bar',
                            'encode', JSONB_BUILD_OBJECT('x','dim_0','y','count')
                        ))
                    )
                ),
                'won_value', JSONB_BUILD_OBJECT(
                    'kind','number','title','Won Value',
                    'lql', FORMAT(
                        'table(%L) | filter((r)->{r.stage=="won"}) | aggregate(@{"value": sum(r.value)})',
                        p_table_id
                    ),
                    'field','value','format','$,.0f'
                ),
                'recent', JSONB_BUILD_OBJECT(
                    'kind','list','title','Recent Deals',
                    'lql', FORMAT('table(%L) | limit(10)', p_table_id),
                    'columns', '[]'::JSONB
                )
            )
         ),
         p_created_by, p_created_by);

        UPDATE public.table_views
        SET config = '["Pipeline","Sales Dashboard"]'::JSONB,
            updated_by = p_created_by, updated_at = NOW()
        WHERE workspace_id = p_workspace_id
          AND table_id = p_table_id
          AND name = '__order__';

        v_default_view_name := 'Pipeline';
    END IF;

    -- 6. Default view (skipped for blank — no user views to flag).
    IF v_default_view_name IS NOT NULL THEN
        PERFORM SET_TABLE_DEFAULT_VIEW(
            p_workspace_id, p_table_id, v_default_view_name
        );
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION
CREATE_TABLE_FROM_TEMPLATE(UUID, VARCHAR, VARCHAR, UUID)
TO app;
