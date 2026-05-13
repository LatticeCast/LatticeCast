-- upgrade
-- V41: Move default_view storage onto the __schema__ row.
--
-- Replaces V37/V40's `is_default` BOOLEAN flag on every view row with a
-- single `default_view` string inside the __schema__ row's config. The
-- __schema__ row already exists for every table; piggybacking on it
-- means one UPDATE writes both columns and default view, with no need
-- for a "exactly one" constraint (a single string value is by
-- construction unique).
--
-- New __schema__.config shape:
--   {
--     "columns":      [ {col1}, {col2}, ... ],
--     "default_view": "Sprint Board" | "Schema" | null
--   }
--
-- All functions that touched __schema__.config (V38 create_table,
-- V39 add/update/delete_column) are rewritten to read/write the
-- `columns` key instead of the bare array.

-- ── 1. Reshape existing __schema__ rows: array → {columns, default_view}
UPDATE public.table_views
SET
    config = JSONB_BUILD_OBJECT(
        'columns',
        CASE
            WHEN JSONB_TYPEOF(config) = 'array' THEN config
            WHEN JSONB_TYPEOF(config) = 'object'
                THEN COALESCE(config -> 'columns', '[]'::JSONB)
            ELSE '[]'::JSONB
        END,
        'default_view',
        NULL::JSONB
    )
WHERE name = '__schema__';

-- ── 2. Backfill default_view from existing is_default flags
WITH defaults AS (
    SELECT
        workspace_id,
        table_id,
        CASE WHEN name = '__schema__' THEN 'Schema' ELSE name END AS view_name
    FROM public.table_views
    WHERE is_default
)

UPDATE public.table_views AS s
SET config = JSONB_SET(s.config, '{default_view}', TO_JSONB(d.view_name))
FROM defaults AS d
WHERE
    s.workspace_id = d.workspace_id
    AND s.table_id = d.table_id
    AND s.name = '__schema__';

-- ── 3. Drop V37/V40: is_default flag + partial unique index + old fn
DROP INDEX IF EXISTS public.table_views_one_default;
ALTER TABLE public.table_views DROP COLUMN IF EXISTS is_default;
DROP FUNCTION IF EXISTS public.set_table_default_view(UUID, VARCHAR, VARCHAR);

-- ── 4. New helper: set/clear the default view on the __schema__ row
CREATE OR REPLACE FUNCTION SET_TABLE_DEFAULT_VIEW(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_view_name VARCHAR
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_target VARCHAR;
BEGIN
    -- 'Schema' is the FE display name for the __schema__ row itself.
    IF p_view_name = 'Schema' THEN
        v_target := 'Schema';
    ELSE
        -- Validate the named user view exists.
        IF NOT EXISTS (
            SELECT 1 FROM public.table_views
            WHERE workspace_id = p_workspace_id
              AND table_id = p_table_id
              AND name = p_view_name
              AND type IN ('table', 'kanban', 'timeline', 'dashboard')
        ) THEN
            RAISE EXCEPTION
                'View "%" not found for table %',
                p_view_name, p_table_id;
        END IF;
        v_target := p_view_name;
    END IF;

    UPDATE public.table_views
    SET config = JSONB_SET(config, '{default_view}', TO_JSONB(v_target)),
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';
END;
$$;

GRANT EXECUTE ON FUNCTION
SET_TABLE_DEFAULT_VIEW(UUID, VARCHAR, VARCHAR) TO app;

-- ── 5. Rewrite create_table_from_template (V38) for new __schema__ shape
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

    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    v_columns := _BUILD_TEMPLATE_COLUMNS(p_kind);
    v_col_ids := _COLUMNS_NAME_MAP(v_columns);

    -- New shape: {columns, default_view}
    UPDATE public.table_views
    SET config = JSONB_BUILD_OBJECT(
            'columns', v_columns,
            'default_view', NULL::JSONB
        ),
        updated_by = p_created_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    FOR v_col IN SELECT * FROM JSONB_ARRAY_ELEMENTS(v_columns) LOOP
        v_col_id := v_col->>'column_id';
        v_col_type := v_col->>'type';
        IF v_col_type IN
           ('number','date','select','tags','text','string','url','checkbox') THEN
            v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, v_col_id);
            PERFORM CREATE_ROW_DATA_INDEX(
                v_idx_name, p_table_id::TEXT, v_col_id, v_col_type
            );
        END IF;
    END LOOP;

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

    IF v_default_view_name IS NOT NULL THEN
        PERFORM SET_TABLE_DEFAULT_VIEW(
            p_workspace_id, p_table_id, v_default_view_name
        );
    END IF;
END;
$$;

-- ── 6. Rewrite V39 column CRUD for new __schema__ shape
CREATE OR REPLACE FUNCTION ADD_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_name TEXT,
    p_type TEXT,
    p_options JSONB,
    p_position INT,
    p_created_by UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_schema JSONB;
    v_columns JSONB;
    v_new_col JSONB;
    v_col_id TEXT;
    v_idx_name TEXT;
    v_position INT;
BEGIN
    SELECT config INTO v_schema
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_schema IS NULL THEN
        RAISE EXCEPTION 'Table % not found (no __schema__ row)', p_table_id;
    END IF;
    v_columns := COALESCE(v_schema->'columns', '[]'::JSONB);
    IF JSONB_TYPEOF(v_columns) <> 'array' THEN
        v_columns := '[]'::JSONB;
    END IF;

    v_position := COALESCE(p_position, JSONB_ARRAY_LENGTH(v_columns));
    v_new_col := _BUILD_COLUMN_DICT(p_name, p_type, p_options, v_position);
    v_col_id := v_new_col->>'column_id';

    UPDATE public.table_views
    SET config = JSONB_SET(
            v_schema, '{columns}',
            v_columns || JSONB_BUILD_ARRAY(v_new_col)
        ),
        updated_by = p_created_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF p_type IN
       ('number','date','select','tags','text','string','url','checkbox') THEN
        v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, v_col_id);
        PERFORM CREATE_ROW_DATA_INDEX(
            v_idx_name, p_table_id::TEXT, v_col_id, p_type
        );
    END IF;

    RETURN v_new_col;
END;
$$;

CREATE OR REPLACE FUNCTION UPDATE_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_column_id TEXT,
    p_patch JSONB,
    p_updated_by UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_schema JSONB;
    v_columns JSONB;
    v_idx INT;
    v_old_col JSONB;
    v_merged JSONB;
    v_new_columns JSONB := '[]'::JSONB;
    v_elem JSONB;
    v_new_type TEXT;
    v_idx_name TEXT;
BEGIN
    SELECT config INTO v_schema
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_schema IS NULL THEN
        RAISE EXCEPTION 'Table % schema missing', p_table_id;
    END IF;
    v_columns := COALESCE(v_schema->'columns', '[]'::JSONB);

    v_idx := NULL;
    FOR v_idx IN
        SELECT ord - 1
        FROM JSONB_ARRAY_ELEMENTS(v_columns) WITH ORDINALITY AS t(elem, ord)
        WHERE elem->>'column_id' = p_column_id
        LIMIT 1
    LOOP
        v_old_col := v_columns->v_idx;
    END LOOP;

    IF v_old_col IS NULL THEN
        RAISE EXCEPTION 'Column % not found in %', p_column_id, p_table_id;
    END IF;

    v_merged := v_old_col || (p_patch - 'column_id' - 'created_at');
    v_merged := JSONB_SET(v_merged, ARRAY['column_id'], v_old_col->'column_id');
    IF v_old_col ? 'created_at' THEN
        v_merged := JSONB_SET(
            v_merged, ARRAY['created_at'], v_old_col->'created_at'
        );
    END IF;

    FOR v_elem IN
        SELECT
            CASE WHEN (ord - 1) = v_idx THEN v_merged ELSE elem END
        FROM JSONB_ARRAY_ELEMENTS(v_columns) WITH ORDINALITY AS t(elem, ord)
        ORDER BY ord
    LOOP
        v_new_columns := v_new_columns || JSONB_BUILD_ARRAY(v_elem);
    END LOOP;

    UPDATE public.table_views
    SET config = JSONB_SET(v_schema, '{columns}', v_new_columns),
        updated_by = p_updated_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    v_new_type := v_merged->>'type';
    IF v_new_type IS NOT NULL
       AND v_new_type <> COALESCE(v_old_col->>'type', '') THEN
        v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, p_column_id);
        PERFORM DROP_ROW_DATA_INDEX(v_idx_name);
        IF v_new_type IN
           ('number','date','select','tags','text','string','url','checkbox') THEN
            PERFORM CREATE_ROW_DATA_INDEX(
                v_idx_name, p_table_id::TEXT, p_column_id, v_new_type
            );
        END IF;
    END IF;

    RETURN v_merged;
END;
$$;

CREATE OR REPLACE FUNCTION DELETE_COLUMN(
    p_workspace_id UUID,
    p_table_id VARCHAR,
    p_column_id TEXT,
    p_updated_by UUID
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_schema JSONB;
    v_columns JSONB;
    v_filtered JSONB;
    v_idx_name TEXT;
    v_removed_count INT;
BEGIN
    SELECT config INTO v_schema
    FROM public.table_views
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';

    IF v_schema IS NULL THEN
        RAISE EXCEPTION 'Table % schema missing', p_table_id;
    END IF;
    v_columns := COALESCE(v_schema->'columns', '[]'::JSONB);

    SELECT COALESCE(JSONB_AGG(elem), '[]'::JSONB)
    INTO v_filtered
    FROM JSONB_ARRAY_ELEMENTS(v_columns) AS elem
    WHERE elem->>'column_id' <> p_column_id;

    v_removed_count := JSONB_ARRAY_LENGTH(v_columns) - JSONB_ARRAY_LENGTH(v_filtered);
    IF v_removed_count = 0 THEN
        RAISE EXCEPTION 'Column % not found in %', p_column_id, p_table_id;
    END IF;

    v_idx_name := _BUILD_RD_IDX_NAME(p_table_id, p_column_id);
    PERFORM DROP_ROW_DATA_INDEX(v_idx_name);

    UPDATE public.table_views
    SET config = JSONB_SET(v_schema, '{columns}', v_filtered),
        updated_by = p_updated_by,
        updated_at = NOW()
    WHERE workspace_id = p_workspace_id
      AND table_id = p_table_id
      AND name = '__schema__';
END;
$$;
