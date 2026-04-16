-- upgrade
-- Migrate users table: switch PK from VARCHAR email to UUID.
--
-- Steps:
--   1. Add user_uuid UUID column, populate for all existing rows
--   2. Update workspace_members.user_id to UUID
--   3. Swap users PK: user_id (email) -> email, user_uuid -> user_id (UUID)
--
-- user_info is NOT created here. See V10__user_info_and_gdpr.sql.

-- ── Step 1: Add user_uuid column ─────────────────────────────────────────────

ALTER TABLE users
ADD COLUMN IF NOT EXISTS user_uuid UUID DEFAULT gen_random_uuid();

UPDATE users SET user_uuid = gen_random_uuid()
WHERE user_uuid IS NULL;

ALTER TABLE users ALTER COLUMN user_uuid SET NOT NULL;

ALTER TABLE users ADD CONSTRAINT uq_users_user_uuid UNIQUE (user_uuid);

-- ── Step 2: Migrate workspace_members.user_id to UUID ────────────────────────

-- Drop old FK and index
ALTER TABLE workspace_members
DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;
DROP INDEX IF EXISTS idx_workspace_members_user_id;

-- Add UUID column and populate from users lookup
ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS user_uuid UUID;

UPDATE workspace_members wm
SET user_uuid = u.user_uuid
FROM users AS u
WHERE wm.user_id = u.user_id;

-- Drop old composite PK
ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_pkey;

-- Make user_uuid NOT NULL and promote
ALTER TABLE workspace_members ALTER COLUMN user_uuid SET NOT NULL;
ALTER TABLE workspace_members DROP COLUMN user_id;
ALTER TABLE workspace_members RENAME COLUMN user_uuid TO user_id;

-- Re-add PK and index
ALTER TABLE workspace_members ADD PRIMARY KEY (workspace_id, user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members (
    user_id
);

-- ── Step 3: Swap users PK from VARCHAR email → UUID ──────────────────────────

-- Drop old PK (users.user_id VARCHAR)
ALTER TABLE users DROP CONSTRAINT users_pkey;

-- Rename columns: old user_id → email, user_uuid → user_id
ALTER TABLE users RENAME COLUMN user_id TO email;
ALTER TABLE users RENAME COLUMN user_uuid TO user_id;

-- Drop FKs that reference the unique constraint (needed before dropping it)
ALTER TABLE workspace_members
DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey;

-- Drop the unique constraint (PK replaces it for uniqueness enforcement)
ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_user_uuid;

-- New PK on UUID column
ALTER TABLE users ADD PRIMARY KEY (user_id);

-- Email index; dropped in V12 along with the email column.
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

-- Re-add FK from workspace_members.user_id → users.user_id (UUID)
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_user_id_fkey
FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE;
