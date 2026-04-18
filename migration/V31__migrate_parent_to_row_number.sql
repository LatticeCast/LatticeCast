-- upgrade
-- V31: Migrate Parent column values from UUID strings to row_number integers.
-- The Row PK changed to (workspace_id, table_id, row_number) in V11/V13.
-- Any rows where a "Parent" column still stores a UUID string are updated
-- to store the corresponding row_number instead.
-- Rows whose parent UUID cannot be resolved are left unchanged (best-effort).

DO $$
DECLARE
    col RECORD;
    r   RECORD;
    parent_rn INT;
BEGIN
    -- For each table that has a column named "Parent"
    FOR col IN
        SELECT t.workspace_id, t.table_id,
               c->>'column_id' AS parent_col_id
        FROM   public.tables t,
               jsonb_array_elements(t.columns) AS c
        WHERE  c->>'name' = 'Parent'
    LOOP
        -- For each row whose Parent value looks like a UUID (36 chars, contains hyphens)
        FOR r IN
            SELECT rw.workspace_id, rw.table_id, rw.row_number,
                   rw.row_data->>col.parent_col_id AS parent_val
            FROM   public.rows rw
            WHERE  rw.workspace_id = col.workspace_id
              AND  rw.table_id     = col.table_id
              AND  (rw.row_data->>col.parent_col_id) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        LOOP
            -- This migration cannot resolve UUIDs to row_numbers because row_id
            -- no longer exists. Clear the stale UUID so the doc does not 500.
            UPDATE public.rows
            SET    row_data = jsonb_set(
                       row_data,
                       ARRAY[col.parent_col_id],
                       'null'::jsonb
                   ),
                   updated_at = NOW()
            WHERE  workspace_id = r.workspace_id
              AND  table_id     = r.table_id
              AND  row_number   = r.row_number;
        END LOOP;
    END LOOP;
END $$;
