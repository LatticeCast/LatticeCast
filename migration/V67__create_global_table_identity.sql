-- upgrade
-- Maintenance window, step 2: the new parent table.
--
-- table_id becomes the identity: a database-assigned BIGINT primary key, stable
-- for the life of the table. Renaming is then an ordinary UPDATE of one row,
-- children reference the id without ON UPDATE CASCADE, and the per-column row
-- indexes keyed by table_id never need rewriting when a table is renamed.
--
-- table_name is what humans and LatticeQL use. It inherits the old table_id
-- values when the rows are moved, which is why existing LatticeQL text keeps
-- resolving after the cutover.

CREATE TABLE IF NOT EXISTS public.tables (
    table_id     BIGINT      GENERATED ALWAYS AS IDENTITY,
    workspace_id UUID        NOT NULL,
    table_name   TEXT        NOT NULL,
    config       JSONB       NOT NULL DEFAULT '{"columns": [], "view_order": [], "default_view": null}'::JSONB,
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tables_pkey PRIMARY KEY (table_id),
    CONSTRAINT tables_workspace_name_key UNIQUE (workspace_id, table_name),
    CONSTRAINT tables_table_name_no_dot CHECK (position('.' IN table_name) = 0),
    CONSTRAINT tables_table_name_not_blank CHECK (btrim(table_name) <> ''),
    CONSTRAINT tables_workspace_fkey FOREIGN KEY (workspace_id)
        REFERENCES public.workspaces (workspace_id) ON DELETE CASCADE
);

-- The workspace_id prefix of the unique index is what serves per-workspace
-- listing and the RLS predicate; no separate index is needed.

-- V15's default privileges only cover objects created BY role dba, and these
-- are created by dba_user, so the grants are explicit. INSERT into an identity
-- column takes USAGE on the sequence.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tables TO app, mgr;
GRANT USAGE ON SEQUENCE public.tables_table_id_seq TO app, mgr;

-- Enabled without policies until V69 installs them: deny-all is the right
-- default while the window is open.
ALTER TABLE public.tables ENABLE ROW LEVEL SECURITY;
