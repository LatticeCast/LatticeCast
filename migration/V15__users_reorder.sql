-- upgrade
-- 0015_users_reorder.sql
-- Reorder users columns: user_id first, add UNIQUE(user_id, role)

CREATE TABLE users_new (
    user_id    UUID NOT NULL DEFAULT gen_random_uuid(),
    role       VARCHAR NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id)
);

INSERT INTO users_new (user_id, role, created_at, updated_at)
SELECT user_id, role, created_at, updated_at FROM users;

-- Drop old table (CASCADE drops FKs referencing it)
DROP TABLE users CASCADE;
ALTER TABLE users_new RENAME TO users;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

-- Add unique constraint on (user_id, role)
ALTER TABLE users ADD CONSTRAINT uq_users_id_role UNIQUE (user_id, role);

-- Recreate FKs from other tables
ALTER TABLE user_info ADD CONSTRAINT user_info_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
ALTER TABLE rows ADD CONSTRAINT rows_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE rows ADD CONSTRAINT rows_updated_by_fkey
    FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL;
