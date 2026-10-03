-- `kind` is a frontend editor/picker hint only.  The blob API never branches
-- on it.  Rename the old misleading `doc` hint to `text` (plain text,
-- Markdown, or CSV) in persisted schemas and in future template output.
--
-- This changes no column name.  Some legacy configurations predate V39 and
-- already contain duplicate normalized names; the V39 trigger must not block
-- this otherwise-independent metadata rewrite.  Migrations run one file per
-- transaction, so a failure rolls back both the UPDATE and trigger state.

ALTER TABLE public.tables DISABLE TRIGGER trg_tables_validate_column_names;

UPDATE public.tables AS table_data
SET config = jsonb_set(
    table_data.config,
    '{columns}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN entry.column_data ->> 'type' = 'blob'
                     AND entry.column_data -> 'options' ->> 'kind' = 'doc'
                THEN jsonb_set(entry.column_data, '{options,kind}', '"text"'::JSONB)
                ELSE entry.column_data
            END
            ORDER BY entry.ordinality
        )
        FROM jsonb_array_elements(table_data.config -> 'columns')
            WITH ORDINALITY AS entry(column_data, ordinality)
    )
)
WHERE EXISTS (
    SELECT 1
    FROM jsonb_array_elements(table_data.config -> 'columns') AS entry(column_data)
    WHERE entry.column_data ->> 'type' = 'blob'
      AND entry.column_data -> 'options' ->> 'kind' = 'doc'
);

ALTER TABLE public.tables ENABLE TRIGGER trg_tables_validate_column_names;

CREATE OR REPLACE FUNCTION public.create_table_from_template(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_kind         VARCHAR,
    p_by           UUID
) RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_result   JSONB;
    v_columns  JSONB;
    v_col      JSONB;
    v_col_id   TEXT;
    v_col_type TEXT;
    v_idx_name TEXT;
BEGIN
    INSERT INTO public.tables (workspace_id, table_id)
    VALUES (p_workspace_id, p_table_id);

    CASE p_kind
        WHEN 'blank' THEN v_result := _seed_blank(p_workspace_id, p_table_id, p_by);
        WHEN 'pm' THEN v_result := _seed_pm(p_workspace_id, p_table_id, p_by);
        WHEN 'crm' THEN v_result := _seed_crm(p_workspace_id, p_table_id, p_by);
        WHEN 'workflow' THEN v_result := _seed_workflow(p_workspace_id, p_table_id, p_by);
        ELSE RAISE EXCEPTION 'unknown template kind: %', p_kind;
    END CASE;

    SELECT jsonb_agg(
        CASE
            WHEN column_entry.column_data ->> 'type' = 'doc' THEN jsonb_set(
                jsonb_set(column_entry.column_data, '{type}', '"blob"'::JSONB),
                '{options}', coalesce(column_entry.column_data -> 'options', '{}'::JSONB)
                    || '{"kind":"text"}'::JSONB
            )
            WHEN column_entry.column_data ->> 'type' = 'blob'
                 AND column_entry.column_data -> 'options' ->> 'kind' = 'doc'
            THEN jsonb_set(column_entry.column_data, '{options,kind}', '"text"'::JSONB)
            ELSE column_entry.column_data
        END
        ORDER BY column_entry.ordinality
    )
    INTO v_columns
    FROM jsonb_array_elements(v_result -> 'columns')
        WITH ORDINALITY AS column_entry(column_data, ordinality);
    v_result := jsonb_set(v_result, '{columns}', v_columns);

    UPDATE public.tables
    SET config = v_result, updated_by = p_by, updated_at = now()
    WHERE workspace_id = p_workspace_id AND table_id = p_table_id;

    FOR v_col IN SELECT * FROM jsonb_array_elements(v_result -> 'columns') LOOP
        v_col_id := v_col ->> 'column_id';
        v_col_type := v_col ->> 'type';
        IF v_col_type IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := public._build_rd_idx_name(p_workspace_id, p_table_id, v_col_id);
            PERFORM public.create_row_data_index(
                p_workspace_id, v_idx_name, p_table_id, v_col_id, v_col_type
            );
        END IF;
    END LOOP;
END;
$$;
