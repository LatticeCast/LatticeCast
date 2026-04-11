-- 0024_lowercase_table_ids.sql
-- Convert all table_id to lowercase (rows FK must be updated too)

-- 1. Update rows first (FK references)
UPDATE rows SET table_id = LOWER(table_id) WHERE table_id != LOWER(table_id);

-- 2. Update tables PK
UPDATE tables SET table_id = LOWER(table_id) WHERE table_id != LOWER(table_id);
