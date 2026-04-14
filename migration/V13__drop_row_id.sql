-- upgrade
-- 0013_drop_row_id.sql
-- Remove row_id UUID column — PK is (table_id, row_number) now

DROP INDEX IF EXISTS idx_rows_row_id;
ALTER TABLE rows DROP COLUMN IF EXISTS row_id;
