-- upgrade
-- Schema state of a table, kept as a single JSONB document:
--   {
--     "columns":      [{column_id, name, type, options}, ...],
--     "view_order":   [view_id, ...],
--     "default_view": view_id | null
--   }
-- One row per (workspace_id, table_id), auto-created by trigger when a
-- row appears in public.tables (so direct INSERTs always have a
-- matching schema). The template seeders (V12) then UPDATE the config
-- with the seeded columns and views.

CREATE TABLE IF NOT EXISTS public.table_schemas (
    workspace_id UUID      NOT NULL,
    table_id     VARCHAR   NOT NULL,
    config       JSONB     NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, table_id),
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id) ON DELETE CASCADE
);

-- ── Auto-create empty schema row on tables INSERT ───────────────────────────

CREATE OR REPLACE FUNCTION public.trg_create_table_schema_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.table_schemas (workspace_id, table_id, config)
    VALUES (
        NEW.workspace_id,
        NEW.table_id,
        jsonb_build_object(
            'columns',      '[]'::JSONB,
            'view_order',   '[]'::JSONB,
            'default_view', NULL
        )
    )
    ON CONFLICT (workspace_id, table_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tables_create_table_schema ON public.tables;
CREATE TRIGGER trg_tables_create_table_schema
AFTER INSERT ON public.tables
FOR EACH ROW EXECUTE FUNCTION public.trg_create_table_schema_fn();
