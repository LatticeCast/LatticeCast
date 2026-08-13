-- upgrade
-- Store documents as a `blob` column with `options.kind = doc`. Existing cell
-- values remain their storage keys but gain the common one-file metadata shape.

WITH doc_columns AS (
    SELECT
        tables.workspace_id,
        tables.table_id,
        doc_column.column_data ->> 'column_id' AS column_id
    FROM public.tables AS tables
    CROSS JOIN LATERAL jsonb_array_elements(tables.config -> 'columns') AS doc_column(column_data)
    WHERE doc_column.column_data ->> 'type' = 'doc'
),

migrated_rows AS (
    SELECT
        rows.workspace_id,
        rows.table_id,
        rows.row_id,
        doc_columns.column_id,
        rows.row_data -> doc_columns.column_id AS old_value
    FROM doc_columns
    INNER JOIN public.rows AS rows
        ON doc_columns.workspace_id = rows.workspace_id
        AND doc_columns.table_id = rows.table_id
    WHERE jsonb_typeof(rows.row_data -> doc_columns.column_id) = 'string'
)

UPDATE public.rows AS rows
SET row_data = jsonb_set(
    rows.row_data,
    ARRAY[migrated_rows.column_id],
    jsonb_build_object(
        'key', migrated_rows.old_value #>> '{}',
        'filename', 'doc.md',
        'content_type', 'text/markdown',
        'size', 0
    )
)
FROM migrated_rows
WHERE rows.workspace_id = migrated_rows.workspace_id
  AND rows.table_id = migrated_rows.table_id
  AND rows.row_id = migrated_rows.row_id;

UPDATE public.tables AS tables
SET config = jsonb_set(
    tables.config,
    '{columns}',
    (
        SELECT jsonb_agg(
            CASE WHEN column_entry.column_data ->> 'type' = 'doc' THEN
                jsonb_set(
                    jsonb_set(column_entry.column_data, '{type}', '"blob"'::JSONB),
                    '{options}',
                    coalesce(column_entry.column_data -> 'options', '{}'::JSONB)
                        || '{"kind":"doc","accept":"text/markdown,.md"}'::JSONB
                )
            ELSE column_entry.column_data END
            ORDER BY column_entry.ordinality
        )
        FROM jsonb_array_elements(tables.config -> 'columns')
            WITH ORDINALITY AS column_entry(column_data, ordinality)
    )
);
