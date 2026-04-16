-- upgrade
-- 0019_table_id_string.sql
-- Change table_id from UUID to VARCHAR (= the table name, human-readable PK)
-- Drop table_name column (table_id IS the name now)

-- 1. Add new string table_id column
ALTER TABLE tables ADD COLUMN IF NOT EXISTS table_id_new VARCHAR;

-- 2. Populate from table_name or name (whichever exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tables' AND column_name='table_name') THEN
    UPDATE tables SET table_id_new = table_name WHERE table_id_new IS NULL;
  ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tables' AND column_name='name') THEN
    UPDATE tables SET table_id_new = name WHERE table_id_new IS NULL;
  END IF;
END $$;

-- Handle duplicates: append workspace_id prefix if names collide globally
UPDATE tables t1
SET table_id_new = t1.table_id_new || '-' || LEFT(t1.workspace_id::TEXT, 8)
WHERE EXISTS (
    SELECT 1 FROM tables AS t2
    WHERE
        t2.table_id_new = t1.table_id_new
        AND t2.table_id != t1.table_id
);

-- 3. Update rows FK: add new column, populate, drop old
ALTER TABLE rows ADD COLUMN IF NOT EXISTS table_id_new VARCHAR;
UPDATE rows r SET
    table_id_new = (
        SELECT t.table_id_new FROM tables AS t
        WHERE t.table_id = r.table_id
    );

-- 4. Drop old constraints and columns
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_table_id_fkey;
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_pkey;
DROP INDEX IF EXISTS idx_rows_table_id;

ALTER TABLE rows DROP COLUMN IF EXISTS table_id;
ALTER TABLE rows RENAME COLUMN table_id_new TO table_id;

-- 5. Drop old table_id and rename
ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_pkey;
ALTER TABLE tables DROP CONSTRAINT IF EXISTS uq_tables_workspace_name;
DROP INDEX IF EXISTS idx_tables_workspace_id;

ALTER TABLE tables DROP COLUMN table_id;
ALTER TABLE tables RENAME COLUMN table_id_new TO table_id;

-- Drop table_name/name if still exists
ALTER TABLE tables DROP COLUMN IF EXISTS table_name;
ALTER TABLE tables DROP COLUMN IF EXISTS name;

-- 6. Set NOT NULL and new PK
ALTER TABLE tables ALTER COLUMN table_id SET NOT NULL;
ALTER TABLE tables ADD PRIMARY KEY (table_id);

-- Unique within workspace
ALTER TABLE tables ADD CONSTRAINT uq_tables_workspace_id UNIQUE (
    workspace_id, table_id
);
CREATE INDEX IF NOT EXISTS idx_tables_workspace_id ON tables (workspace_id);

-- 7. Rows: set NOT NULL, PK, FK
ALTER TABLE rows ALTER COLUMN table_id SET NOT NULL;
ALTER TABLE rows ADD PRIMARY KEY (table_id, row_number);
ALTER TABLE rows ADD CONSTRAINT rows_table_id_fkey
FOREIGN KEY (table_id) REFERENCES tables (table_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_rows_table_id ON rows (table_id);

-- 8. Recreate trigger (row_number auto-increment)
DROP TRIGGER IF EXISTS trg_rows_row_number ON rows;
CREATE TRIGGER trg_rows_row_number
BEFORE INSERT ON rows
FOR EACH ROW EXECUTE FUNCTION TRG_SET_ROW_NUMBER_FN();
