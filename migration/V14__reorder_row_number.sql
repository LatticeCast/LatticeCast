-- upgrade
-- 0014_reorder_row_number.sql
-- Move row_number to second column position (after table_id)
-- PG doesn't support column reorder natively — recreate table

CREATE TABLE rows_new (
    table_id   UUID NOT NULL,
    row_number BIGINT NOT NULL DEFAULT 0,
    row_data   JSONB NOT NULL DEFAULT '{}',
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (table_id, row_number)
);

INSERT INTO rows_new (table_id, row_number, row_data, created_by, updated_by, created_at, updated_at)
SELECT table_id, row_number, row_data, created_by, updated_by, created_at, updated_at FROM rows;

DROP TABLE rows CASCADE;
ALTER TABLE rows_new RENAME TO rows;

-- Recreate FKs
ALTER TABLE rows ADD CONSTRAINT rows_table_id_fkey
    FOREIGN KEY (table_id) REFERENCES tables(table_id) ON DELETE CASCADE;
ALTER TABLE rows ADD CONSTRAINT rows_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE rows ADD CONSTRAINT rows_updated_by_fkey
    FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL;

-- Recreate trigger
DROP TRIGGER IF EXISTS trg_rows_row_number ON rows;
CREATE TRIGGER trg_rows_row_number
    BEFORE INSERT ON rows
    FOR EACH ROW EXECUTE FUNCTION trg_set_row_number_fn();

-- Recreate table_id index
CREATE INDEX IF NOT EXISTS idx_rows_table_id ON rows(table_id);
