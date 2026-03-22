-- 001_create_users.sql
-- Users table: email is the unique identity across all login methods

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR PRIMARY KEY,  -- email address (same user regardless of login method)
    name VARCHAR NOT NULL DEFAULT '',
    role VARCHAR NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

-- Seed admin users via scripts/dev_seed.sql (not in migration)
