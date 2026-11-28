-- Two holes around a column type change.
--
-- 1. The rows trigger read the column types without a lock, so an insert could
--    be checked against the old type while the type changed under it. It now
--    reads FOR KEY SHARE, which waits for update_column's FOR UPDATE.
--    (V83's comment that every row writer already took that lock was wrong:
--    only the API's PATCH and PUT did.)
-- 2. A per-column index outlived the type it was built for and refused valid
--    writes, e.g. a long numeric string in a column that had been int.
--    update_column now drops it.

CREATE OR REPLACE FUNCTION public.trg_check_row_data_fn()
 RETURNS TRIGGER
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_columns JSONB;
    v_changed JSONB := NEW.row_data;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        SELECT coalesce(jsonb_object_agg(cell.key, cell.value), '{}'::JSONB)
        INTO   v_changed
        FROM   jsonb_each(NEW.row_data) AS cell
        WHERE  cell.value IS DISTINCT FROM OLD.row_data -> cell.key;

        IF v_changed = '{}'::JSONB THEN
            RETURN NEW;
        END IF;
    END IF;

    SELECT config -> 'columns'
    INTO   v_columns
    FROM   public.tables
    WHERE  table_id = NEW.table_id
    FOR KEY SHARE;

    IF v_columns IS NOT NULL THEN
        NEW.row_data := NEW.row_data || public._check_row_data(v_columns, v_changed);
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.update_column(p_workspace_id UUID, p_table_id BIGINT, p_column_id TEXT, p_patch JSONB, p_by UUID)
 RETURNS JSONB
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_old_columns JSONB;
    v_new_columns JSONB;
    v_found       BOOLEAN := FALSE;
    v_new_cfg     JSONB;
    v_old_type    TEXT;
    v_bad         BIGINT;
BEGIN
    SELECT config -> 'columns'
    INTO   v_old_columns
    FROM   public.tables
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    -- The rows trigger reads this row FOR KEY SHARE, so no write slips past the check.
    FOR UPDATE;

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

    SELECT c ->> 'type'
    INTO   v_old_type
    FROM   jsonb_array_elements(v_old_columns) AS c
    WHERE  c ->> 'column_id' = p_column_id;

    IF p_patch ? 'type' AND p_patch ->> 'type' IS DISTINCT FROM v_old_type THEN
        SELECT count(*)
        INTO   v_bad
        FROM   public.rows
        WHERE  table_id = p_table_id
        AND    NOT public._column_value_fits(p_patch ->> 'type', row_data -> p_column_id);

        IF v_bad > 0 THEN
            RAISE EXCEPTION 'cannot change type to %: % stored value(s) do not fit it',
                p_patch ->> 'type', v_bad
                USING ERRCODE = 'invalid_parameter_value';
        END IF;

        -- An index built for the old type must not outlive it.
        IF to_regclass('public.' || quote_ident(public._build_rd_idx_name(p_workspace_id, p_table_id, p_column_id)))
               IS NOT NULL
           OR to_regclass('public.' || quote_ident(public._build_rd_idx_name(p_table_id, p_column_id)))
               IS NOT NULL THEN
            PERFORM public.drop_row_data_index(
                p_workspace_id,
                public._build_rd_idx_name(p_workspace_id, p_table_id, p_column_id),
                p_table_id,
                p_column_id
            );
        END IF;
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
