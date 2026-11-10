-- Query rows across selected tables or workspaces under the caller's RLS identity.
-- The function is SECURITY INVOKER: app_user remains subject to rows/tables RLS.

CREATE OR REPLACE FUNCTION public.query_rows(
    p_table_ids     BIGINT[] DEFAULT NULL,
    p_workspace_ids UUID[]   DEFAULT NULL,
    p_page          INTEGER  DEFAULT NULL,
    p_page_size     INTEGER  DEFAULT NULL,
    p_sort_by       TEXT     DEFAULT 'row_id',
    p_desc          BOOLEAN  DEFAULT TRUE,
    p_filter_json   JSONB    DEFAULT '{}'::JSONB,
    p_include_total BOOLEAN  DEFAULT FALSE
) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_source      TEXT;
    v_filter      JSONB;
    v_sort        TEXT;
    v_array_sort  TEXT;
    v_direction   TEXT;
    v_query       TEXT;
    v_limit       BIGINT;
    v_offset      BIGINT;
    v_page        INTEGER;
    v_items       JSONB;
    v_has_more    BOOLEAN := FALSE;
    v_total       BIGINT;
    v_total_pages BIGINT;
BEGIN
    IF (p_table_ids IS NULL) = (p_workspace_ids IS NULL) THEN
        RAISE EXCEPTION 'provide exactly one of table_ids or workspace_ids'
            USING ERRCODE = '22023';
    END IF;

    IF p_table_ids IS NOT NULL THEN
        IF COALESCE(array_ndims(p_table_ids), 0) <> 1
           OR cardinality(p_table_ids) NOT BETWEEN 1 AND 100
           OR array_position(p_table_ids, NULL) IS NOT NULL
           OR EXISTS (SELECT 1 FROM unnest(p_table_ids) AS id WHERE id <= 0)
        THEN
            RAISE EXCEPTION 'table_ids must contain 1 to 100 positive ids'
                USING ERRCODE = '22023';
        END IF;
        v_source := 'FROM public.rows AS r '
                 || 'WHERE r.table_id = ANY($1)';
    ELSE
        IF COALESCE(array_ndims(p_workspace_ids), 0) <> 1
           OR cardinality(p_workspace_ids) NOT BETWEEN 1 AND 100
           OR array_position(p_workspace_ids, NULL) IS NOT NULL
        THEN
            RAISE EXCEPTION 'workspace_ids must contain 1 to 100 ids'
                USING ERRCODE = '22023';
        END IF;
        v_source := 'FROM public.rows AS r '
                 || 'JOIN public.tables AS t ON t.table_id = r.table_id '
                 || 'WHERE t.workspace_id = ANY($2)';
    END IF;

    IF p_page_size IS NULL THEN
        IF p_page IS NOT NULL THEN
            RAISE EXCEPTION 'page requires page_size'
                USING ERRCODE = '22023';
        END IF;
    ELSIF p_page_size NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'page_size must be between 1 and 200'
            USING ERRCODE = '22023';
    END IF;

    v_page := CASE WHEN p_page_size IS NULL THEN NULL
                   ELSE COALESCE(p_page, 1) END;
    IF v_page IS NOT NULL AND v_page < 1 THEN
        RAISE EXCEPTION 'page must be at least 1'
            USING ERRCODE = '22023';
    END IF;

    IF p_sort_by IS NULL OR p_sort_by NOT IN
       ('row_id', 'table_id', 'created_at', 'updated_at')
    THEN
        RAISE EXCEPTION 'invalid sort_by'
            USING ERRCODE = '22023';
    END IF;

    v_filter := COALESCE(p_filter_json, '{}'::JSONB);
    IF jsonb_typeof(v_filter) <> 'object' THEN
        RAISE EXCEPTION 'filter_json must be a JSON object'
            USING ERRCODE = '22023';
    END IF;
    IF v_filter <> '{}'::JSONB THEN
        v_source := v_source || ' AND r.row_data @> $3';
    END IF;

    v_direction := CASE WHEN COALESCE(p_desc, TRUE)
                        THEN 'DESC' ELSE 'ASC' END;
    -- Only a validated column identifier and a fixed direction enter SQL.
    v_sort := format('r.%I %s, r.table_id %s, r.row_id %s',
                     p_sort_by, v_direction, v_direction, v_direction);
    v_array_sort := format('q.%I %s, q.table_id %s, q.row_id %s',
                           p_sort_by, v_direction, v_direction, v_direction);

    IF p_page_size IS NOT NULL THEN
        v_limit := p_page_size::BIGINT + 1;
        v_offset := (v_page::BIGINT - 1) * p_page_size;
    END IF;

    v_query := 'SELECT COALESCE('
            || 'jsonb_agg(to_jsonb(q) ORDER BY ' || v_array_sort || '), '
            || '''[]''::JSONB) '
            || 'FROM (SELECT r.* ' || v_source
            || ' ORDER BY ' || v_sort;
    IF p_page_size IS NOT NULL THEN
        v_query := v_query || ' LIMIT $4 OFFSET $5';
    END IF;
    v_query := v_query || ') AS q';

    EXECUTE v_query INTO v_items
        USING p_table_ids, p_workspace_ids, v_filter, v_limit, v_offset;

    IF p_page_size IS NOT NULL
       AND jsonb_array_length(v_items) > p_page_size
    THEN
        v_has_more := TRUE;
        v_items := v_items - p_page_size;
    END IF;

    IF COALESCE(p_include_total, FALSE) THEN
        IF p_page_size IS NULL THEN
            v_total := jsonb_array_length(v_items);
        ELSE
            EXECUTE 'SELECT count(*) ' || v_source INTO v_total
                USING p_table_ids, p_workspace_ids, v_filter;
            v_total_pages := ceiling(v_total::NUMERIC / p_page_size);
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'items',       v_items,
        'page',        v_page,
        'page_size',   p_page_size,
        'has_more',    v_has_more,
        'total',       v_total,
        'total_pages', v_total_pages
    );
END;
$function$;

REVOKE ALL ON
    FUNCTION public.query_rows(
        BIGINT[], UUID[], INTEGER, INTEGER, TEXT, BOOLEAN, JSONB, BOOLEAN
    ) FROM public;
GRANT EXECUTE ON
    FUNCTION public.query_rows(
        BIGINT[], UUID[], INTEGER, INTEGER, TEXT, BOOLEAN, JSONB, BOOLEAN
    ) TO app;
