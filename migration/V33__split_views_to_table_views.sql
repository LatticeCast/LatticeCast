-- upgrade
-- V33: Split tables.views JSONB into a dedicated public.table_views table.
--
-- Goals:
--   - Per-view audit, locking, indexing.
--   - Linked-list ordering via next_view_id (FE walks the chain).
--   - "Exactly one default per table" via partial unique index on is_default.
--   - "At least one view always exists" via:
--       * BEFORE-DELETE trigger refusing to delete the default view.
--       * AFTER-INSERT trigger on tables auto-creating a default view.
--
-- Order: all DDL first, then backfill DML, to avoid deferred-FK conflict
-- with ALTER TABLE ENABLE RLS.

-- 1. New table ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.table_views (
    workspace_id UUID      NOT NULL,
    table_id     VARCHAR   NOT NULL,
    view_number  BIGINT    NOT NULL,
    is_default   BOOLEAN   NOT NULL DEFAULT false,
    next_view_id BIGINT,
    name         VARCHAR   NOT NULL,
    type         VARCHAR   NOT NULL,
    config       JSONB     NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, table_id, view_number),
    CONSTRAINT table_views_table_fkey
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id)
    ON DELETE CASCADE,
    CONSTRAINT table_views_next_fkey
    FOREIGN KEY (workspace_id, table_id, next_view_id)
    REFERENCES public.table_views (workspace_id, table_id, view_number)
    DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT table_views_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES auth.users (user_id),
    CONSTRAINT table_views_updated_by_fkey
    FOREIGN KEY (updated_by) REFERENCES auth.users (user_id),
    CONSTRAINT table_views_name_unique
    UNIQUE (workspace_id, table_id, name)
);

-- "exactly one default per table" — partial unique index
CREATE UNIQUE INDEX IF NOT EXISTS table_views_one_default
ON public.table_views (workspace_id, table_id)
WHERE is_default;

-- 2. Trigger: auto-set view_number on INSERT ---------------------------------

CREATE OR REPLACE FUNCTION TRG_SET_VIEW_NUMBER_FN()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.view_number IS NULL THEN
        SELECT COALESCE(MAX(view_number), 0) + 1
        INTO NEW.view_number
        FROM public.table_views
        WHERE workspace_id = NEW.workspace_id
          AND table_id = NEW.table_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_table_views_view_number ON public.table_views;
CREATE TRIGGER trg_table_views_view_number
BEFORE INSERT ON public.table_views
FOR EACH ROW EXECUTE FUNCTION TRG_SET_VIEW_NUMBER_FN();

-- 3. Trigger: refuse to delete the default view ------------------------------

CREATE OR REPLACE FUNCTION TRG_PREVENT_DEFAULT_VIEW_DELETE_FN()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_default THEN
        RAISE EXCEPTION
            'Cannot delete default view (workspace=%, table=%, view=%)',
            OLD.workspace_id, OLD.table_id, OLD.view_number;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_table_views_prevent_default_delete
ON public.table_views;
CREATE TRIGGER trg_table_views_prevent_default_delete
BEFORE DELETE ON public.table_views
FOR EACH ROW EXECUTE FUNCTION TRG_PREVENT_DEFAULT_VIEW_DELETE_FN();

-- 4. Trigger: auto-create default view on table INSERT -----------------------

CREATE OR REPLACE FUNCTION TRG_CREATE_DEFAULT_VIEW_FN()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.table_views (
        workspace_id, table_id, is_default, name, type, config
    ) VALUES (
        NEW.workspace_id, NEW.table_id, true, 'Table', 'table', '{}'::jsonb
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tables_create_default_view ON public.tables;
CREATE TRIGGER trg_tables_create_default_view
AFTER INSERT ON public.tables
FOR EACH ROW EXECUTE FUNCTION TRG_CREATE_DEFAULT_VIEW_FN();

-- 5. Row-Level Security ------------------------------------------------------

ALTER TABLE public.table_views ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS table_views_workspace_member ON public.table_views;
CREATE POLICY table_views_workspace_member ON public.table_views
FOR ALL
USING (
    CHECK_WORKSPACE_MEMBER(
        workspace_id,
        NULLIF(CURRENT_SETTING('app.current_user_id', true), '')::UUID
    )
);

-- 6. Grants (defensive — ALTER DEFAULT PRIVILEGES already covers new tables)

GRANT SELECT, INSERT, UPDATE, DELETE ON public.table_views TO app;

-- 7. Backfill from tables.views JSONB ----------------------------------------
-- Done after DDL so deferred-FK events do not conflict with ALTER TABLE above.
-- view_number supplied explicitly → trg_set_view_number_fn is a no-op here.

INSERT INTO public.table_views (
    workspace_id, table_id, view_number, is_default,
    name, type, config
)
SELECT
    t.workspace_id,
    t.table_id,
    v.ord AS view_number,
    v.ord = 1 AS is_default,
    COALESCE(v.elem ->> 'name', 'View ' || v.ord::TEXT) AS name,
    COALESCE(v.elem ->> 'type', 'table') AS type,
    COALESCE(v.elem -> 'config', '{}'::JSONB) AS config
FROM public.tables AS t
CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS(
    COALESCE(t.views, '[]'::JSONB)
) WITH ORDINALITY AS v (elem, ord);

-- Set next_view_id pointers from view_number ordering
UPDATE public.table_views AS curr
SET next_view_id = nxt.view_number
FROM public.table_views AS nxt
WHERE
    curr.workspace_id = nxt.workspace_id
    AND curr.table_id = nxt.table_id
    AND nxt.view_number = curr.view_number + 1;

-- Tables that had no views in JSONB get a default
INSERT INTO public.table_views (
    workspace_id, table_id, view_number, is_default, name, type, config
)
SELECT
    t.workspace_id,
    t.table_id,
    1 AS view_number,
    true AS is_default,
    'Table' AS name,
    'table' AS type,
    '{}'::JSONB AS config
FROM public.tables AS t
WHERE NOT EXISTS (
    SELECT 1 FROM public.table_views AS v
    WHERE v.workspace_id = t.workspace_id AND v.table_id = t.table_id
);

-- 8. Drop the old views column -----------------------------------------------

ALTER TABLE public.tables DROP COLUMN IF EXISTS views;
