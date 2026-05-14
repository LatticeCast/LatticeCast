-- upgrade
-- Views per table. Composite PK (workspace_id, table_id, view_id);
-- view_id is a per-(workspace_id, table_id) auto-increment BIGINT
-- starting at 1, set by BEFORE INSERT trigger. The view's name and
-- type live inside `config` JSONB along with view-specific settings.

CREATE TABLE IF NOT EXISTS public.table_views (
    workspace_id UUID      NOT NULL,
    table_id     VARCHAR   NOT NULL,
    view_id      BIGINT    NOT NULL DEFAULT 1,
    config       JSONB     NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, table_id, view_id),
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id) ON DELETE CASCADE
);

-- ── view_id auto-increment ──────────────────────────────────────────────────
-- Per-(workspace_id, table_id) numbering. Same pattern as rows.row_id.

CREATE OR REPLACE FUNCTION public.trg_set_view_id_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.view_id IS NULL OR NEW.view_id = 0 THEN
        SELECT COALESCE(MAX(view_id), 0) + 1
        INTO   NEW.view_id
        FROM   public.table_views
        WHERE  workspace_id = NEW.workspace_id
        AND    table_id     = NEW.table_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_set_view_id ON public.table_views;
CREATE TRIGGER trg_set_view_id
BEFORE INSERT ON public.table_views
FOR EACH ROW EXECUTE FUNCTION public.trg_set_view_id_fn();
