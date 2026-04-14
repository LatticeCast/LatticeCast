-- upgrade
-- 0024_lowercase_table_ids.sql
-- Convert all table_id to lowercase

-- Drop FK first
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_table_id_fkey;

-- Update tables PK
UPDATE tables SET table_id = LOWER(table_id) WHERE table_id != LOWER(table_id);

-- Update rows FK
UPDATE rows SET table_id = LOWER(table_id) WHERE table_id != LOWER(table_id);

-- Recreate FK
ALTER TABLE rows ADD CONSTRAINT rows_table_id_fkey
    FOREIGN KEY (table_id) REFERENCES tables(table_id) ON DELETE CASCADE;
