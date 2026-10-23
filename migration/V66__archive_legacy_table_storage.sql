-- upgrade
-- Maintenance window, step 1: move the name-keyed storage aside.
--
-- Before this cutover the table identity IS the table's name: public.tables.table_id
-- is a VARCHAR that doubles as the URL slug and as the LatticeQL table name.
-- After it, table_id is a database-assigned BIGINT identity and the name lives
-- in table_name, so every table that stores a table_id has to be rebuilt with
-- the new type.
--
-- The old storage is renamed, not dropped: these migrations only reshape the
-- schema. Moving the rows is a separate, resumable script, because loaded data
-- succeeding and migrated data are two different claims.
--
-- The archive keeps its primary keys, but their constraint names are renamed so
-- the new tables can take the canonical names. Renaming a primary key
-- constraint renames the backing index with it.

ALTER TABLE public.tables RENAME TO tables_old;
ALTER TABLE public.rows RENAME TO rows_old;
ALTER TABLE public.table_views RENAME TO table_views_old;
ALTER TABLE private.table_row_counters RENAME TO table_row_counters_old;
ALTER TABLE private.blob_objects RENAME TO blob_objects_old;

ALTER TABLE public.tables_old RENAME CONSTRAINT tables_pkey TO tables_old_pkey;
ALTER TABLE public.rows_old RENAME CONSTRAINT rows_pkey TO rows_old_pkey;
ALTER TABLE public.table_views_old RENAME CONSTRAINT table_views_pkey TO table_views_old_pkey;
ALTER TABLE private.table_row_counters_old
    RENAME CONSTRAINT table_row_counters_pkey TO table_row_counters_old_pkey;
ALTER TABLE private.blob_objects_old
    RENAME CONSTRAINT blob_objects_pkey TO blob_objects_old_pkey;

-- The archive is frozen. Its triggers would call the functions V69 rebuilds
-- against the new tables, and nothing writes to it again.
DROP TRIGGER IF EXISTS trg_rows_row_id ON public.rows_old;
DROP TRIGGER IF EXISTS trg_rows_canonical_ts ON public.rows_old;
DROP TRIGGER IF EXISTS trg_rows_retire_blobs ON public.rows_old;
DROP TRIGGER IF EXISTS trg_set_view_id ON public.table_views_old;
DROP TRIGGER IF EXISTS trg_tables_validate_column_names ON public.tables_old;

-- Close the archive for business. mgr matters as much as app here: mgr_user is
-- BYPASSRLS, so leaving it with SELECT would let a bug read the pre-cutover
-- tables and hide the fact that the new ones are not being written.
REVOKE ALL ON public.tables_old FROM app, mgr;
REVOKE ALL ON public.rows_old FROM app, mgr;
REVOKE ALL ON public.table_views_old FROM app, mgr;
REVOKE ALL ON private.table_row_counters_old FROM app, mgr;
REVOKE ALL ON private.blob_objects_old FROM app, mgr;
