-- V30: add ON UPDATE CASCADE to rows + table_views FKs
--
-- Both child tables reference public.tables(workspace_id, table_id)
-- with ON DELETE CASCADE but default ON UPDATE NO ACTION. Renaming
-- a table_id fails with ForeignKeyViolationError when rows or views
-- exist. Adding ON UPDATE CASCADE lets PG propagate the rename.

-- ── rows FK ──────────────────────────────────────────────────────────

DO $$
DECLARE
    v_name TEXT;
BEGIN
    SELECT conname INTO v_name
    FROM   pg_constraint
    WHERE  conrelid  = 'public.rows'::regclass
    AND    contype   = 'f'
    AND    confrelid = 'public.tables'::regclass;

    IF v_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE public.rows DROP CONSTRAINT %I',
            v_name
        );
    END IF;
END $$;

ALTER TABLE public.rows
ADD CONSTRAINT rows_workspace_id_table_id_fkey
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id)
    ON DELETE CASCADE ON UPDATE CASCADE;

-- ── table_views FK ───────────────────────────────────────────────────

DO $$
DECLARE
    v_name TEXT;
BEGIN
    SELECT conname INTO v_name
    FROM   pg_constraint
    WHERE  conrelid  = 'public.table_views'::regclass
    AND    contype   = 'f'
    AND    confrelid = 'public.tables'::regclass;

    IF v_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE public.table_views '
            'DROP CONSTRAINT %I',
            v_name
        );
    END IF;
END $$;

ALTER TABLE public.table_views
ADD CONSTRAINT table_views_workspace_id_table_id_fkey
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id)
    ON DELETE CASCADE ON UPDATE CASCADE;
