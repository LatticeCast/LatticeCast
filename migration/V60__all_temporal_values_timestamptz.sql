-- upgrade
-- Every persisted application instant is PostgreSQL TIMESTAMPTZ.
--
-- Historical TIMESTAMP WITHOUT TIME ZONE values represent UTC. Attach that
-- offset without shifting the stored instant, then use CURRENT_TIMESTAMP for
-- timestamp defaults. JSONB row date/datetime cells are intentionally
-- excluded: their canonical representation is an epoch-millisecond number.

CREATE TEMP TABLE _temporal_columns ON COMMIT DROP AS
SELECT
    c.table_schema,
    c.table_name,
    c.column_name,
    c.data_type,
    c.column_default IS NOT NULL AS had_default
FROM information_schema.columns AS c
WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
  AND c.data_type IN ('timestamp without time zone', 'timestamp with time zone');

DO $$
DECLARE
    column_data RECORD;
BEGIN
    FOR column_data IN
        SELECT *
        FROM _temporal_columns
        WHERE data_type = 'timestamp without time zone'
        ORDER BY table_schema, table_name, column_name
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I ALTER COLUMN %I DROP DEFAULT',
            column_data.table_schema, column_data.table_name, column_data.column_name
        );
        EXECUTE format(
            'ALTER TABLE %I.%I ALTER COLUMN %I TYPE TIMESTAMPTZ '
            'USING (%I AT TIME ZONE ''UTC'')',
            column_data.table_schema,
            column_data.table_name,
            column_data.column_name,
            column_data.column_name
        );
        IF column_data.had_default THEN
            EXECUTE format(
                'ALTER TABLE %I.%I ALTER COLUMN %I SET DEFAULT CURRENT_TIMESTAMP',
                column_data.table_schema, column_data.table_name, column_data.column_name
            );
        END IF;
    END LOOP;
END;
$$;
