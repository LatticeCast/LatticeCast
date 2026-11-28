-- Every write path checks a cell against its column's storage type, not only
-- int: text takes a string, double a number, strings an array of strings, and
-- null is always allowed.
--
-- Only cells the write changes are checked. A value stored before this rule
-- therefore never blocks an edit to another cell of its row. Columns still on
-- an old type, and blob columns (written by update_blob_cell), are not checked.

CREATE OR REPLACE FUNCTION public._check_row_data(p_columns JSONB, p_data JSONB)
 RETURNS JSONB
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_column JSONB;
    v_id     TEXT;
    v_type   TEXT;
    v_value  JSONB;
BEGIN
    FOR v_column IN
        SELECT column_data
        FROM jsonb_array_elements(p_columns) AS column_data
        WHERE column_data ->> 'type' IN ('text', 'int', 'double', 'strings')
          AND p_data ? (column_data ->> 'column_id')
    LOOP
        v_id    := v_column ->> 'column_id';
        v_type  := v_column ->> 'type';
        v_value := p_data -> v_id;

        -- An emptied number cell is null, and an integral 3.0 is stored as 3.
        IF v_type IN ('int', 'double')
           AND jsonb_typeof(v_value) = 'string'
           AND btrim(v_value #>> '{}') = '' THEN
            p_data := jsonb_set(p_data, ARRAY[v_id], 'null'::JSONB);
            CONTINUE;
        END IF;

        IF NOT public._column_value_fits(v_type, v_value) THEN
            RAISE EXCEPTION '% column "%" does not take %', v_type, v_column ->> 'name', v_value
                USING ERRCODE = 'invalid_parameter_value';
        END IF;

        IF v_type = 'int' AND jsonb_typeof(v_value) = 'number' THEN
            p_data := jsonb_set(p_data, ARRAY[v_id], to_jsonb((v_value #>> '{}')::NUMERIC::BIGINT));
        END IF;
    END LOOP;

    RETURN p_data;
END;
$function$;

REVOKE ALL    ON FUNCTION public._check_row_data(JSONB, JSONB) FROM public;
GRANT EXECUTE ON FUNCTION public._check_row_data(JSONB, JSONB) TO app, mgr;

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
    WHERE  table_id = NEW.table_id;

    IF v_columns IS NOT NULL THEN
        NEW.row_data := NEW.row_data || public._check_row_data(v_columns, v_changed);
    END IF;

    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.trg_check_row_data_fn() FROM public;

DROP TRIGGER IF EXISTS trg_rows_coerce_ints ON public.rows;
DROP TRIGGER IF EXISTS trg_rows_check_types ON public.rows;
CREATE TRIGGER trg_rows_check_types
    BEFORE INSERT OR UPDATE OF row_data ON public.rows
    FOR EACH ROW EXECUTE FUNCTION public.trg_check_row_data_fn();

-- The trigger is the one place the rule lives: the write functions no longer
-- check on their own.
CREATE OR REPLACE FUNCTION public.patch_row_data(p_workspace_id UUID, p_table_id BIGINT, p_row_id BIGINT, p_patch JSONB)
 RETURNS public.ROWS
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


CREATE OR REPLACE FUNCTION public.put_row_data(p_workspace_id UUID, p_table_id BIGINT, p_row_id BIGINT, p_data JSONB)
 RETURNS public.ROWS
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


DROP FUNCTION IF EXISTS public.trg_coerce_row_data_ints_fn();
DROP FUNCTION IF EXISTS public._coerce_row_data_ints(JSONB, JSONB);
