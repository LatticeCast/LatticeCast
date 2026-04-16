-- upgrade
-- V29: Change tables PK from (table_id) to (workspace_id, table_id)
-- Allows same table name in different workspaces (e.g. two "ta" tables)

-- 1. Add workspace_id to rows (populated from tables join)
ALTER TABLE rows ADD COLUMN IF NOT EXISTS workspace_id UUID;
UPDATE rows r SET
    workspace_id = (
        SELECT t.workspace_id FROM tables AS t
        WHERE t.table_id = r.table_id
    )
WHERE workspace_id IS NULL;

-- 2. Drop existing constraints on rows
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_table_id_fkey;
ALTER TABLE rows DROP CONSTRAINT IF EXISTS rows_pkey;
DROP INDEX IF EXISTS idx_rows_table_id;

-- 3. Drop existing constraints on tables
ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_pkey;
ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_new_pkey;
ALTER TABLE tables DROP CONSTRAINT IF EXISTS uq_tables_workspace_id;

-- 4. New composite PK on tables
ALTER TABLE tables ADD PRIMARY KEY (workspace_id, table_id);

-- 5. rows: set NOT NULL, new composite PK and FK
ALTER TABLE rows ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE rows ADD PRIMARY KEY (workspace_id, table_id, row_number);
ALTER TABLE rows ADD CONSTRAINT rows_table_fkey
FOREIGN KEY (workspace_id, table_id)
REFERENCES tables (workspace_id, table_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_rows_workspace_table
ON rows (workspace_id, table_id);

-- 6. Update row_number trigger to scope by (workspace_id, table_id)
CREATE OR REPLACE FUNCTION trg_set_row_number_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT COALESCE(MAX(row_number), 0) + 1
    INTO NEW.row_number
    FROM rows
    WHERE workspace_id = NEW.workspace_id
      AND table_id = NEW.table_id;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rows_row_number ON rows;
CREATE TRIGGER trg_rows_row_number
BEFORE INSERT ON rows
FOR EACH ROW EXECUTE FUNCTION trg_set_row_number_fn();

-- 7. Update RLS helper — table_id alone no longer unique
CREATE OR REPLACE FUNCTION get_table_workspace_id(ws_id UUID, t_id TEXT)
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT workspace_id FROM public.tables
    WHERE workspace_id = ws_id AND table_id = t_id;
$$;

-- 8. Recreate rows RLS policy using workspace_id directly
DROP POLICY IF EXISTS rows_workspace_member ON public.rows;
CREATE POLICY rows_workspace_member ON public.rows
FOR ALL
USING (
    check_workspace_member(
        workspace_id,
        current_setting('app.current_user_id', TRUE)::UUID
    )
);

-- 9. Re-grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app;
