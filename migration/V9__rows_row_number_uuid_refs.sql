-- upgrade
-- 0009_rows_row_number_uuid_refs.sql
-- L-82: Add per-table row_number, convert created_by/updated_by to UUID FKs

-- ── 1. Add row_number column ────────────────────────────────────────────────

ALTER TABLE rows ADD COLUMN IF NOT EXISTS row_number BIGINT NOT NULL DEFAULT 0;

-- ── 2. Backfill row_number for existing rows (per table_id, ordered by
--      created_at, row_id) ─────────────────────────────────────────────────

UPDATE rows r
SET row_number = sub.rn
FROM (
    SELECT
        row_id,
        ROW_NUMBER()
            OVER (PARTITION BY table_id ORDER BY created_at, row_id)
            AS rn
    FROM rows
) AS sub
WHERE r.row_id = sub.row_id;

-- ── 3. Unique constraint: (table_id, row_number) ─────────────────────────────

ALTER TABLE rows
DROP CONSTRAINT IF EXISTS uq_rows_table_row_number;
ALTER TABLE rows
ADD CONSTRAINT uq_rows_table_row_number UNIQUE (table_id, row_number);

-- ── 4. Trigger function: auto-set row_number on INSERT ───────────────────────

CREATE OR REPLACE FUNCTION TRG_SET_ROW_NUMBER_FN()
RETURNS TRIGGER AS $$
BEGIN
    SELECT COALESCE(MAX(row_number), 0) + 1 INTO NEW.row_number
    FROM rows
    WHERE table_id = NEW.table_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rows_row_number ON rows;
CREATE TRIGGER trg_rows_row_number
BEFORE INSERT ON rows
FOR EACH ROW EXECUTE FUNCTION TRG_SET_ROW_NUMBER_FN();

-- ── 5. Convert created_by/updated_by VARCHAR → nullable UUID FK ──────────────

-- Drop NOT NULL and default so we can change the type
ALTER TABLE rows ALTER COLUMN created_by DROP NOT NULL;
ALTER TABLE rows ALTER COLUMN created_by DROP DEFAULT;
ALTER TABLE rows ALTER COLUMN updated_by DROP NOT NULL;
ALTER TABLE rows ALTER COLUMN updated_by DROP DEFAULT;

-- Cast valid UUID strings to UUID, set non-UUID values (e.g. email strings)
-- to NULL
ALTER TABLE rows
ALTER COLUMN created_by TYPE UUID
USING CASE
    WHEN
        created_by
        ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN created_by::UUID
END;

ALTER TABLE rows
ALTER COLUMN updated_by TYPE UUID
USING CASE
    WHEN
        updated_by
        ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN updated_by::UUID
END;

-- Add FK constraints (ON DELETE SET NULL so rows survive user deletion)
ALTER TABLE rows
DROP CONSTRAINT IF EXISTS rows_created_by_fkey;
ALTER TABLE rows
ADD CONSTRAINT rows_created_by_fkey
FOREIGN KEY (created_by) REFERENCES users (user_id) ON DELETE SET NULL;

ALTER TABLE rows
DROP CONSTRAINT IF EXISTS rows_updated_by_fkey;
ALTER TABLE rows
ADD CONSTRAINT rows_updated_by_fkey
FOREIGN KEY (updated_by) REFERENCES users (user_id) ON DELETE SET NULL;
