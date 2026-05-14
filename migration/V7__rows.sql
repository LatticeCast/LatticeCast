-- upgrade
-- Row storage. row_data is a JSONB blob keyed by column_id; per-column
-- GIN/btree partial indexes are created by public.create_row_data_index
-- as columns are added. row_id is a per-(workspace_id, table_id)
-- auto-increment BIGINT set by BEFORE INSERT trigger.

CREATE TABLE IF NOT EXISTS public.rows (
    workspace_id UUID      NOT NULL,
    table_id     VARCHAR   NOT NULL,
    row_id       BIGINT    NOT NULL DEFAULT 0,
    row_data     JSONB     NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, table_id, row_id),
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id) ON DELETE CASCADE
);

-- ── row_id auto-increment ───────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.trg_set_row_id_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.row_id IS NULL OR NEW.row_id = 0 THEN
        SELECT COALESCE(MAX(row_id), 0) + 1
        INTO   NEW.row_id
        FROM   public.rows
        WHERE  workspace_id = NEW.workspace_id
        AND    table_id     = NEW.table_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rows_row_id ON public.rows;
CREATE TRIGGER trg_rows_row_id
BEFORE INSERT ON public.rows
FOR EACH ROW EXECUTE FUNCTION public.trg_set_row_id_fn();
