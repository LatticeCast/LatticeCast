-- upgrade
-- Drop tables.table_name — unused after name simplification.
-- CASCADE removes uq_tables_workspace_name UNIQUE constraint (from V18).

ALTER TABLE tables DROP COLUMN IF EXISTS table_name CASCADE;
