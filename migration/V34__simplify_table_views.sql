-- upgrade
-- V34: Simplify table_views — collapse schema, view-order, and views into one
-- discriminated table.
--
-- Replaces V33's linked-list / is_default / view_number machinery with a
-- single (workspace_id, table_id, name) PK and a `type` column whose value
-- determines what `config` means:
--   - type='schema' (name='__schema__'): config = column array (replaces
--     tables.columns)
--   - type='order' (name='__order__'): config = ordered name array (e.g.
--     ["Sprint Board", "Roadmap"])
--   - type='kanban' | 'timeline' | 'dashboard' | 'table' (user names):
--     config = view-specific config blob
--
-- The schema row IS the implicit Table-rendering default and cannot be
-- deleted.

-- 1. Drop V33 triggers and the deferred self-FK FIRST. The DELETE in step 2
--    would otherwise queue deferred FK events that block the ALTER TABLE
--    statements in step 3.
DROP TRIGGER IF EXISTS trg_table_views_view_number ON public.table_views;
DROP TRIGGER IF EXISTS trg_table_views_prevent_default_delete
ON public.table_views;
DROP TRIGGER IF EXISTS trg_tables_create_default_view ON public.tables;
DROP FUNCTION IF EXISTS trg_set_view_number_fn();
DROP FUNCTION IF EXISTS trg_prevent_default_view_delete_fn();
DROP FUNCTION IF EXISTS trg_create_default_view_fn();
ALTER TABLE public.table_views
DROP CONSTRAINT IF EXISTS table_views_next_fkey;

-- 2. Wipe V33-era data: there is no production DB yet; user-created views
--    backfilled by V33 are recreated from tables.columns (as the schema
--    row) plus an empty order row.
DELETE FROM public.table_views;

-- 3. Drop V33-specific structure
ALTER TABLE public.table_views DROP CONSTRAINT IF EXISTS table_views_pkey;
ALTER TABLE public.table_views
DROP CONSTRAINT IF EXISTS table_views_name_unique;
DROP INDEX IF EXISTS table_views_one_default;
ALTER TABLE public.table_views DROP COLUMN IF EXISTS view_number;
ALTER TABLE public.table_views DROP COLUMN IF EXISTS next_view_id;
ALTER TABLE public.table_views DROP COLUMN IF EXISTS is_default;

-- 4. New PK is (workspace_id, table_id, name)
ALTER TABLE public.table_views
ADD PRIMARY KEY (workspace_id, table_id, name);

-- 5. Backfill __schema__ rows from tables.columns
INSERT INTO public.table_views (
    workspace_id, table_id, name, type, config
)
SELECT
    workspace_id,
    table_id,
    '__schema__' AS name,
    'schema' AS type,
    COALESCE(columns, '[]'::JSONB) AS config
FROM public.tables
ON CONFLICT (workspace_id, table_id, name) DO NOTHING;

-- 6. Backfill empty __order__ rows
INSERT INTO public.table_views (
    workspace_id, table_id, name, type, config
)
SELECT
    workspace_id,
    table_id,
    '__order__' AS name,
    'order' AS type,
    '[]'::JSONB AS config
FROM public.tables
ON CONFLICT (workspace_id, table_id, name) DO NOTHING;

-- 7. Drop tables.columns — it now lives in the __schema__ row's config
ALTER TABLE public.tables DROP COLUMN IF EXISTS columns;

-- 8. Trigger: refuse to delete the schema row
CREATE OR REPLACE FUNCTION TRG_PREVENT_SCHEMA_DELETE_FN()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.name = '__schema__' THEN
        RAISE EXCEPTION
            'Cannot delete schema row (workspace=%, table=%)',
            OLD.workspace_id, OLD.table_id;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_table_views_prevent_schema_delete
ON public.table_views;
CREATE TRIGGER trg_table_views_prevent_schema_delete
BEFORE DELETE ON public.table_views
FOR EACH ROW EXECUTE FUNCTION TRG_PREVENT_SCHEMA_DELETE_FN();

-- 9. Trigger: AFTER INSERT on tables, auto-create __schema__ + __order__
CREATE OR REPLACE FUNCTION TRG_CREATE_SCHEMA_AND_ORDER_FN()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.table_views (
        workspace_id, table_id, name, type, config
    ) VALUES
        (NEW.workspace_id, NEW.table_id, '__schema__', 'schema', '[]'::JSONB),
        (NEW.workspace_id, NEW.table_id, '__order__', 'order', '[]'::JSONB);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tables_create_schema_and_order ON public.tables;
CREATE TRIGGER trg_tables_create_schema_and_order
AFTER INSERT ON public.tables
FOR EACH ROW EXECUTE FUNCTION TRG_CREATE_SCHEMA_AND_ORDER_FN();

-- 10. Defensive grants (V33 already covers this; harmless re-grant)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.table_views TO app;
