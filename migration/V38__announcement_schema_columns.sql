-- V38 — announcement table schema columns only.
--
-- Remove Doc/Time from the fixed announcement table schema, keep the other
-- existing columns, and refresh the four metadata column rows in
-- public.tables.config->columns by removing any existing copies and
-- appending the desired definitions.

UPDATE public.tables
SET config = jsonb_set(
        config,
        '{columns}',
        (
            SELECT COALESCE(jsonb_agg(column_data ORDER BY ordinality), '[]'::JSONB)
            FROM jsonb_array_elements(config -> 'columns')
                WITH ORDINALITY AS c(column_data, ordinality)
            WHERE column_data ->> 'name' NOT IN (
                'Doc',
                'Time',
                'updated_at',
                'updated_by',
                'created_at',
                'created_by'
            )
        ) || jsonb_build_array(
            public._build_column_dict('updated_at', 'date', '{}'::JSONB),
            public._build_column_dict('updated_by', 'text', '{}'::JSONB),
            public._build_column_dict('created_at', 'date', '{}'::JSONB),
            public._build_column_dict('created_by', 'text', '{}'::JSONB)
        )
    )
WHERE workspace_id = 'f8bb8500-10f2-4e8c-b0a3-0d5c30778086'::UUID
  AND table_id = 'announcement';
