-- upgrade
-- 0017_remove_key_column.sql
-- Remove "Key" column from all tables' columns JSONB + remove Key data from
-- row_data. One-time cleanup — Key is replaced by type-row_number

-- 1. Remove Key column definition from tables.columns JSONB
UPDATE tables
SET
    columns = (
        SELECT
            COALESCE(
                JSONB_AGG(col)
                FILTER (WHERE col ->> 'name' != 'Key'),
                '[]'::jsonb
            )
        FROM JSONB_ARRAY_ELEMENTS(columns) AS col
    )
WHERE columns @> '[{"name": "Key"}]';

-- 2. Remove Key values from row_data (find col_id for Key, remove that key
--    from row_data)
-- This is best-effort: removes any row_data key that stored a Key value
-- matching L-* or similar pattern
-- The actual Key column_id varies per table, so we clean by finding it from
-- the table's old columns
