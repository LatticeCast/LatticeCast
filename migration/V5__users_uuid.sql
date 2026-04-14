-- upgrade
-- 0005_users_uuid.sql
-- Migrate users table: add UUID PK, create user_info table
-- Steps:
--   1. Add user_uuid UUID column, populate for all existing rows
--   2. Create user_info (user_id UUID FK, display_id, email, name)
--   3. Populate user_info from existing users
--   4. Update workspace_members.user_id to UUID
--   5. Swap users PK from VARCHAR email → UUID

-- ── Step 1: Add user_uuid column ─────────────────────────────────────────────

ALTER TABLE users ADD COLUMN IF NOT EXISTS user_uuid UUID DEFAULT gen_random_uuid();

UPDATE users SET user_uuid = gen_random_uuid() WHERE user_uuid IS NULL;

ALTER TABLE users ALTER COLUMN user_uuid SET NOT NULL;

ALTER TABLE users ADD CONSTRAINT uq_users_user_uuid UNIQUE (user_uuid);

-- ── Step 2: Create user_info table ───────────────────────────────────────────
-- user_id: UUID FK → users.user_uuid (soon to be users.user_id after PK swap)
-- display_id: lowercase alphanumeric slug, 3-32 chars
-- email: original identifier (email in prod, arbitrary string in dev)

CREATE TABLE IF NOT EXISTS user_info (
    user_id    UUID        NOT NULL,
    display_id VARCHAR(32) NOT NULL CHECK (display_id ~ '^[a-z0-9][a-z0-9_-]{2,31}$'),
    email      VARCHAR     NOT NULL,
    name       VARCHAR     NOT NULL DEFAULT '',
    PRIMARY KEY (user_id),
    UNIQUE (display_id),
    UNIQUE (email),
    FOREIGN KEY (user_id) REFERENCES users(user_uuid) ON DELETE CASCADE
);

-- ── Step 3: Populate user_info from existing users ───────────────────────────
-- display_id: take part before '@', lowercase, replace non-[a-z0-9_-] with '_',
--             pad to min 3 chars, truncate to 32, append row_num suffix for duplicates

INSERT INTO user_info (user_id, display_id, email, name)
SELECT
    u.user_uuid,
    CASE
        WHEN row_num = 1 THEN padded
        ELSE SUBSTRING(padded, 1, 28) || LPAD(CAST(row_num AS VARCHAR), 1, '0')
    END,
    u.user_id,
    u.name
FROM (
    SELECT
        user_uuid,
        user_id,
        name,
        CASE
            WHEN LENGTH(raw_slug) < 3 THEN RPAD(raw_slug, 3, '0')
            ELSE raw_slug
        END AS padded,
        ROW_NUMBER() OVER (
            PARTITION BY CASE
                WHEN LENGTH(raw_slug) < 3 THEN RPAD(raw_slug, 3, '0')
                ELSE raw_slug
            END
            ORDER BY created_at, user_id
        ) AS row_num
    FROM (
        SELECT
            user_uuid,
            user_id,
            name,
            created_at,
            SUBSTRING(
                REGEXP_REPLACE(
                    LOWER(SPLIT_PART(user_id, '@', 1)),
                    '[^a-z0-9_-]', '_', 'g'
                ), 1, 32
            ) AS raw_slug
        FROM users
    ) base
) u
ON CONFLICT DO NOTHING;

-- ── Step 4: Migrate workspace_members.user_id to UUID ────────────────────────

-- Drop old FK and index
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;
DROP INDEX IF EXISTS idx_workspace_members_user_id;

-- Add UUID column and populate from users lookup
ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS user_uuid UUID;

UPDATE workspace_members wm
SET user_uuid = u.user_uuid
FROM users u
WHERE wm.user_id = u.user_id;

-- Drop old composite PK
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_pkey;

-- Make user_uuid NOT NULL and promote
ALTER TABLE workspace_members ALTER COLUMN user_uuid SET NOT NULL;
ALTER TABLE workspace_members DROP COLUMN user_id;
ALTER TABLE workspace_members RENAME COLUMN user_uuid TO user_id;

-- Re-add PK and index
ALTER TABLE workspace_members ADD PRIMARY KEY (workspace_id, user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);

-- ── Step 5: Swap users PK from VARCHAR email → UUID ──────────────────────────

-- Drop old PK (users.user_id VARCHAR)
ALTER TABLE users DROP CONSTRAINT users_pkey;

-- Rename columns: old user_id → email, user_uuid → user_id
ALTER TABLE users RENAME COLUMN user_id TO email;
ALTER TABLE users RENAME COLUMN user_uuid TO user_id;

-- Drop FKs that reference the unique constraint (needed before dropping it)
ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_user_id_fkey;
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;

-- Drop the unique constraint (PK replaces it for uniqueness enforcement)
ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_user_uuid;

-- New PK on UUID column
ALTER TABLE users ADD PRIMARY KEY (user_id);

-- Index on email for lookups
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

-- Re-add FK from workspace_members.user_id → users.user_id (UUID)
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
