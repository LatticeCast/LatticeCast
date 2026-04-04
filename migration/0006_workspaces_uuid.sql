-- 0006_workspaces_uuid.sql
-- Migrate workspaces table: add UUID PK, create workspace_info table
-- Steps:
--   1. Add ws_uuid UUID column, populate for all existing rows
--   2. Create workspace_info (workspace_id UUID FK, display_id, name)
--   3. Populate workspace_info from existing workspaces
--   4. Migrate workspace_members.workspace_id to UUID
--   5. Migrate tables.workspace_id to UUID
--   6. Swap workspaces PK from VARCHAR → UUID

-- ── Step 1: Add ws_uuid column ─────────────────────────────────────────────

ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS ws_uuid UUID DEFAULT gen_random_uuid();

UPDATE workspaces SET ws_uuid = gen_random_uuid() WHERE ws_uuid IS NULL;

ALTER TABLE workspaces ALTER COLUMN ws_uuid SET NOT NULL;

ALTER TABLE workspaces ADD CONSTRAINT uq_workspaces_ws_uuid UNIQUE (ws_uuid);

-- ── Step 2: Create workspace_info table ──────────────────────────────────────
-- workspace_id: UUID FK → workspaces.ws_uuid (soon to be workspaces.workspace_id after PK swap)
-- display_id: URL-safe slug derived from old workspace_id (email, UUID, UUID/name patterns)
-- name: workspace display name

CREATE TABLE IF NOT EXISTS workspace_info (
    workspace_id UUID        NOT NULL,
    display_id   VARCHAR(128) NOT NULL CHECK (display_id ~ '^[a-z0-9][a-z0-9._@/-]{0,127}$'),
    name         VARCHAR     NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_id),
    UNIQUE (display_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(ws_uuid) ON DELETE CASCADE
);

-- ── Step 3: Populate workspace_info from existing workspaces ─────────────────
-- display_id: lowercase original workspace_id, replace chars outside [a-z0-9._@/-] with '-',
--             ensure starts with [a-z0-9], append row_num suffix for duplicates

INSERT INTO workspace_info (workspace_id, display_id, name)
SELECT
    ws_uuid,
    CASE
        WHEN row_num = 1 THEN slugged
        ELSE SUBSTRING(slugged, 1, 124) || '-' || LPAD(CAST(row_num AS VARCHAR), 3, '0')
    END,
    name
FROM (
    SELECT
        ws_uuid,
        name,
        slugged,
        ROW_NUMBER() OVER (
            PARTITION BY slugged
            ORDER BY created_at, workspace_id
        ) AS row_num
    FROM (
        SELECT
            ws_uuid,
            name,
            created_at,
            workspace_id,
            SUBSTRING(
                REGEXP_REPLACE(
                    LOWER(workspace_id),
                    '[^a-z0-9._@/-]', '-', 'g'
                ), 1, 128
            ) AS slugged
        FROM workspaces
    ) base
) u
ON CONFLICT DO NOTHING;

-- ── Step 4: Migrate workspace_members.workspace_id to UUID ───────────────────

-- Drop old FK (references old VARCHAR PK)
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_workspace_id_fkey;

-- Add UUID column and populate from workspaces lookup
ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS workspace_uuid UUID;

UPDATE workspace_members wm
SET workspace_uuid = w.ws_uuid
FROM workspaces w
WHERE wm.workspace_id = w.workspace_id;

-- Drop old composite PK
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_pkey;

-- Make workspace_uuid NOT NULL and promote
ALTER TABLE workspace_members ALTER COLUMN workspace_uuid SET NOT NULL;
ALTER TABLE workspace_members DROP COLUMN workspace_id;
ALTER TABLE workspace_members RENAME COLUMN workspace_uuid TO workspace_id;

-- Re-add PK (FK will be re-added after step 6)
ALTER TABLE workspace_members ADD PRIMARY KEY (workspace_id, user_id);

-- ── Step 5: Migrate tables.workspace_id to UUID ──────────────────────────────

-- Drop old FK and index
ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_workspace_id_fkey;
DROP INDEX IF EXISTS idx_tables_workspace_id;

-- Add UUID column and populate from workspaces lookup
ALTER TABLE tables ADD COLUMN IF NOT EXISTS workspace_uuid UUID;

UPDATE tables t
SET workspace_uuid = w.ws_uuid
FROM workspaces w
WHERE t.workspace_id = w.workspace_id;

-- Make workspace_uuid NOT NULL and promote
ALTER TABLE tables ALTER COLUMN workspace_uuid SET NOT NULL;
ALTER TABLE tables DROP COLUMN workspace_id;
ALTER TABLE tables RENAME COLUMN workspace_uuid TO workspace_id;

-- Recreate index (FK re-added after step 6)
CREATE INDEX IF NOT EXISTS idx_tables_workspace_id ON tables(workspace_id);

-- ── Step 6: Swap workspaces PK from VARCHAR → UUID ───────────────────────────

-- Drop workspace_info FK first (it depends on the unique constraint we're about to drop)
ALTER TABLE workspace_info DROP CONSTRAINT IF EXISTS workspace_info_workspace_id_fkey;

-- Drop old PK (workspaces.workspace_id VARCHAR)
ALTER TABLE workspaces DROP CONSTRAINT workspaces_pkey;

-- Rename columns: old workspace_id → display_id, ws_uuid → workspace_id
ALTER TABLE workspaces RENAME COLUMN workspace_id TO display_id;
ALTER TABLE workspaces RENAME COLUMN ws_uuid TO workspace_id;

-- Drop unique constraint (PK replaces it)
ALTER TABLE workspaces DROP CONSTRAINT IF EXISTS uq_workspaces_ws_uuid;

-- New PK on UUID column
ALTER TABLE workspaces ADD PRIMARY KEY (workspace_id);

-- Index on display_id for lookups
CREATE INDEX IF NOT EXISTS ix_workspaces_display_id ON workspaces(display_id);

-- ── Step 7: Re-add FK constraints referencing new UUID PK ────────────────────

ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;

ALTER TABLE tables ADD CONSTRAINT tables_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;

-- Fix workspace_info FK: now references workspaces(workspace_id) UUID PK
ALTER TABLE workspace_info DROP CONSTRAINT IF EXISTS workspace_info_workspace_id_fkey;
ALTER TABLE workspace_info ADD CONSTRAINT workspace_info_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE;
