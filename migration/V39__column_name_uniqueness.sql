-- V39 — enforce unique normalized column names in table configurations.
--
-- Column names are user-facing labels stored in tables.config->columns.
-- Normalize them with trim + lowercase so labels such as "Status" and
-- " status " cannot coexist in one table.

CREATE OR REPLACE FUNCTION public._column_names_are_unique(
    p_columns JSONB
) RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(p_columns) = 'array' THEN p_columns
                ELSE '[]'::JSONB
            END
        ) AS column_data
        GROUP BY lower(btrim(COALESCE(column_data ->> 'name', '')))
        HAVING count(*) > 1
    );
$$;

CREATE OR REPLACE FUNCTION public.trg_validate_column_names()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT public._column_names_are_unique(NEW.config -> 'columns') THEN
        RAISE EXCEPTION 'duplicate normalized column name in table config'
            USING ERRCODE = 'unique_violation';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tables_validate_column_names ON public.tables;
CREATE TRIGGER trg_tables_validate_column_names
BEFORE INSERT OR UPDATE OF config ON public.tables
FOR EACH ROW
EXECUTE FUNCTION public.trg_validate_column_names();

REVOKE ALL    ON FUNCTION public._column_names_are_unique(JSONB) FROM public;
REVOKE ALL    ON FUNCTION public.trg_validate_column_names()       FROM public;
GRANT EXECUTE ON FUNCTION public._column_names_are_unique(JSONB) TO app, mgr;
GRANT EXECUTE ON FUNCTION public.trg_validate_column_names()       TO app, mgr;
