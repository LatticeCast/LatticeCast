-- upgrade
-- Maintenance window, step 3: the children of the new identity.
--
-- Same columns and the same row/view identity as before; only table_id changes
-- type and the foreign keys now point at tables(table_id), which is that
-- table's primary key. No composite UNIQUE (workspace_id, table_id) is needed
-- because table_id alone is unique, and with the identity decoupled from the
-- name there is nothing left for ON UPDATE CASCADE to do: a rename is one
-- UPDATE of public.tables and never touches these tables.
--
-- Cost of the single-column foreign key: the database no longer enforces
-- rows.workspace_id = tables.workspace_id. The application always derives the
-- workspace from the resolved table, and RLS still authorises on the row's own
-- workspace_id, so a mismatched row would be authorised by the wrong
-- workspace. Watch for that in review; a BEFORE INSERT/UPDATE check is the
-- alternative if it ever bites.

CREATE TABLE IF NOT EXISTS public.rows (
    workspace_id UUID        NOT NULL,
    table_id     BIGINT      NOT NULL,
    row_id       BIGINT      NOT NULL DEFAULT 0,
    row_data     JSONB       NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- table_id is globally unique, so workspace_id would be a redundant key
    -- component; it stays a column for RLS.
    CONSTRAINT rows_pkey PRIMARY KEY (table_id, row_id),
    CONSTRAINT rows_table_fkey FOREIGN KEY (table_id)
        REFERENCES public.tables (table_id) ON DELETE CASCADE
);

-- RLS predicates filter on workspace_id, so it stays a column and gets its own
-- index: the primary key can no longer serve a workspace-wide scan.
CREATE INDEX IF NOT EXISTS idx_rows_workspace_table
    ON public.rows (workspace_id, table_id);

CREATE TABLE IF NOT EXISTS public.table_views (
    workspace_id UUID        NOT NULL,
    table_id     BIGINT      NOT NULL,
    -- No DEFAULT: V16 dropped V9's DEFAULT 1 because it bypassed the BEFORE
    -- INSERT trigger, so a second view in the same table collided on 1.
    view_id      BIGINT      NOT NULL,
    config       JSONB       NOT NULL DEFAULT '{}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT table_views_pkey PRIMARY KEY (table_id, view_id),
    CONSTRAINT table_views_valid_type CHECK (
        config ->> 'type' IN (
            'table',
            'kanban',
            'timeline',
            'dashboard',
            'workflow'
        )
    ),
    CONSTRAINT table_views_table_fkey FOREIGN KEY (table_id)
        REFERENCES public.tables (table_id) ON DELETE CASCADE
);

-- Same reason as rows: keep the RLS column indexed.
CREATE INDEX IF NOT EXISTS idx_table_views_workspace_table
    ON public.table_views (workspace_id, table_id);

-- Counter rows are reached only through the SECURITY DEFINER trigger
-- function, so neither app nor mgr needs privileges here.
CREATE TABLE IF NOT EXISTS private.table_row_counters (
    workspace_id UUID   NOT NULL,
    table_id     BIGINT NOT NULL,
    last_row_id  BIGINT NOT NULL,
    CONSTRAINT table_row_counters_pkey PRIMARY KEY (workspace_id, table_id),
    CONSTRAINT table_row_counters_table_fkey FOREIGN KEY (table_id)
        REFERENCES public.tables (table_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS private.blob_objects (
    object_key TEXT   NOT NULL,
    workspace_id UUID NOT NULL,
    table_id     BIGINT NOT NULL,
    row_id       BIGINT NOT NULL,
    column_id    TEXT   NOT NULL,
    CONSTRAINT blob_objects_pkey PRIMARY KEY (object_key),
    CONSTRAINT blob_objects_row_fkey FOREIGN KEY (table_id, row_id)
        REFERENCES public.rows (table_id, row_id) ON DELETE CASCADE
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rows TO app, mgr;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.table_views TO app, mgr;
GRANT SELECT, DELETE ON private.blob_objects TO mgr;

ALTER TABLE public.rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.table_views ENABLE ROW LEVEL SECURITY;
