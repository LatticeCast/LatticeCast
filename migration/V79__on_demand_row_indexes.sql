-- Per-column row indexes are created on demand, not on every add_column().
--
-- Rows of every table share one physical table, and a column's type is chosen
-- by the user at run time, so the platform cannot know which columns will ever
-- be filtered on. An index nobody uses still costs every INSERT and UPDATE of
-- every table. Equality on select / tags / checkbox / text is already served
-- by the shared row_data GIN (V72/V77); a per-column btree is only for range
-- queries, and the caller now asks for it explicitly:
--   POST   /tables/{id}/columns/{column_id}/index
--   DELETE /tables/{id}/columns/{column_id}/index
--   GET    /tables/{id}/indexes
-- Existing indexes are left alone.

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

-- The per-column indexes of one table, for a caller that may read its workspace.
CREATE OR REPLACE FUNCTION public.list_row_data_indexes(p_workspace_id uuid, p_table_id bigint)
 RETURNS TABLE(index_name text, method text, size_bytes bigint)
 LANGUAGE plpgsql
 STABLE
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_user_id UUID;
    v_prefix  TEXT;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL
        OR NOT public.check_workspace_permission(p_workspace_id, v_user_id, 'read')
    THEN
        RAISE EXCEPTION 'read permission required for workspace %', p_workspace_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    v_prefix := 'idx_rd_' || left(replace(p_workspace_id::TEXT, '-', ''), 12) || '_' || p_table_id::TEXT || '_';
    RETURN QUERY
    SELECT c.relname::TEXT, am.amname::TEXT, pg_relation_size(c.oid)
    FROM pg_class AS c
    JOIN pg_index AS ix ON ix.indexrelid = c.oid
    JOIN pg_am AS am ON am.oid = c.relam
    WHERE ix.indrelid = 'public.rows'::regclass
      AND starts_with(c.relname::TEXT, v_prefix)
    ORDER BY c.relname;
END;
$function$;

REVOKE ALL ON FUNCTION public.list_row_data_indexes(uuid, bigint) FROM public;
GRANT EXECUTE ON FUNCTION public.list_row_data_indexes(uuid, bigint) TO app;


-- A blank table has no columns: the user decides which to add. The old blank
-- set (Title, Doc, Description) is the `basic` template.
CREATE OR REPLACE FUNCTION public._seed_blank(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    RETURN jsonb_build_object(
        'columns',      '[]'::JSONB,
        'view_order',   '[]'::JSONB,
        'default_view', NULL::JSONB
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public._seed_basic(p_workspace_id uuid, p_table_id bigint, p_by uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    RETURN jsonb_build_object(
        'columns', jsonb_build_array(
            _build_column_dict('Title',       'text', '{}'::JSONB),
            _build_column_dict('Doc',         'blob', '{"kind":"text"}'::JSONB),
            _build_column_dict('Description', 'text', '{}'::JSONB)
        ),
        'view_order',   '[]'::JSONB,
        'default_view', NULL::JSONB
    );
END;
$function$;

-- Same dispatcher as V73 with the `basic` kind, and without the per-column
-- index loop: templates, like add_column, create no index.
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
BEGIN
    -- The id is the database's to assign; the caller only names the table.
    INSERT INTO public.tables (workspace_id, table_name)
    VALUES (p_workspace_id, p_table_name)
    RETURNING table_id INTO v_table_id;

    CASE p_kind
        WHEN 'blank' THEN
            v_result := _seed_blank(p_workspace_id, v_table_id, p_by);
        WHEN 'basic' THEN
            v_result := _seed_basic(p_workspace_id, v_table_id, p_by);
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

    RETURN v_table_id;
END;
$function$;


-- Deleting a table or workspace cascades its rows but not its per-column
-- indexes, which then stay forever: every query on `rows` plans against them
-- and every write evaluates their predicates. This drops up to p_limit indexes
-- whose table no longer exists and returns how many it dropped. Each DROP locks
-- `rows`, and one transaction cannot hold locks for thousands of them, so run
-- it in small batches, one call per transaction, until it returns 0.
CREATE OR REPLACE FUNCTION public.drop_orphan_row_indexes(p_limit integer DEFAULT 100)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_index TEXT;
    v_count INTEGER := 0;
BEGIN
    FOR v_index IN
        SELECT c.relname
        FROM pg_index AS ix
        JOIN pg_class AS c ON c.oid = ix.indexrelid
        CROSS JOIN LATERAL (
            SELECT substring(pg_get_expr(ix.indpred, ix.indrelid) FROM 'table_id = ''?([0-9]+)') AS table_id
        ) AS pred
        WHERE ix.indrelid = 'public.rows'::regclass
          AND starts_with(c.relname::TEXT, 'idx_rd_')
          AND pred.table_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM public.tables AS t WHERE t.table_id = pred.table_id::BIGINT
          )
        LIMIT p_limit
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS public.%I', v_index);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$function$;

REVOKE ALL ON FUNCTION public.drop_orphan_row_indexes(integer) FROM public;
GRANT EXECUTE ON FUNCTION public.drop_orphan_row_indexes(integer) TO mgr;
