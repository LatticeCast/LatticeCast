-- upgrade
-- V35: Drop the trg_prevent_schema_delete trigger introduced in V34.
--
-- The trigger blocked deletion of any '__schema__' row, including the
-- legitimate CASCADE delete that fires when a parent `tables` row is
-- removed. Result: DELETE on a table 500-errors.
--
-- The same invariant ("user can't delete __schema__") is already enforced
-- at the API layer:
--   - router/api/tables.py rejects reserved names in DELETE /views/{name}
--   - There is no generic DELETE endpoint on table_views
-- So the DB-level trigger is redundant. Drop it.

DROP TRIGGER IF EXISTS trg_table_views_prevent_schema_delete
ON public.table_views;
DROP FUNCTION IF EXISTS trg_prevent_schema_delete_fn();
