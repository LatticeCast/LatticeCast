-- upgrade
-- Migration 0025: update Doc columns from type=url to type=doc
-- Targets any column named "Doc" with type "url" in any table's columns JSONB array

UPDATE tables
SET columns = (
    SELECT jsonb_agg(
        CASE
            WHEN col->>'name' = 'Doc' AND col->>'type' = 'url'
            THEN jsonb_set(col, '{type}', '"doc"')
            ELSE col
        END
    )
    FROM jsonb_array_elements(columns) AS col
)
WHERE EXISTS (
    SELECT 1
    FROM jsonb_array_elements(columns) AS col
    WHERE col->>'name' = 'Doc' AND col->>'type' = 'url'
);
