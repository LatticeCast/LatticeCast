-- A column's type may only change when every stored value already fits the new
-- type. Without this, text -> int was accepted over "abc" and the int trigger
-- then refused every later write to that row, whichever cell it touched.
-- Values are never converted here: convert_column_type.py does that.

CREATE OR REPLACE FUNCTION public._column_value_fits(p_type TEXT, p_value JSONB)
 RETURNS BOOLEAN
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'public', 'pg_temp'
AS $function$
    SELECT CASE
        WHEN p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN TRUE
        WHEN p_type = 'text'   THEN jsonb_typeof(p_value) = 'string'
        WHEN p_type = 'double' THEN jsonb_typeof(p_value) = 'number'
        WHEN p_type = 'int'    THEN
            CASE WHEN jsonb_typeof(p_value) = 'number' THEN
                (p_value #>> '{}')::NUMERIC % 1 = 0
                AND (p_value #>> '{}')::NUMERIC
                    BETWEEN -9223372036854775808 AND 9223372036854775807
            ELSE FALSE END
        WHEN p_type = 'strings' THEN
            CASE WHEN jsonb_typeof(p_value) = 'array' THEN
                NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(p_value) AS item
                    WHERE jsonb_typeof(item) <> 'string'
                )
            ELSE FALSE END
        ELSE FALSE
    END;
$function$;

REVOKE ALL    ON FUNCTION public._column_value_fits(TEXT, JSONB) FROM public;
GRANT EXECUTE ON FUNCTION public._column_value_fits(TEXT, JSONB) TO app, mgr;

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
    -- Row writers lock this row FOR KEY SHARE, so none slips in past the check.
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
