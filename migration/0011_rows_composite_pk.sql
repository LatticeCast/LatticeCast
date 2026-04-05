-- 0011_rows_composite_pk.sql
-- Change rows PK from row_id UUID to (table_id, row_number)
-- PG trigger handles per-table auto-increment (already in 0009)

-- 1. Drop old PK
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_pkey;

-- 2. Drop the unique constraint (will be replaced by PK)
ALTER TABLE rows DROP CONSTRAINT IF EXISTS uq_rows_table_row_number;

-- 3. Set new composite PK
ALTER TABLE rows ADD PRIMARY KEY (table_id, row_number);

-- 4. Keep row_id as a regular column (not PK, but still unique for backward compat)
CREATE UNIQUE INDEX IF NOT EXISTS idx_rows_row_id ON rows(row_id);
