-- 0010_user_info.sql
-- L-84: Add user_info table (user_id UUID FK → users, display_id, email, name)

-- ── 1. Create user_info table ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_info (
    user_id     UUID         NOT NULL,
    display_id  VARCHAR(128) NOT NULL CHECK (display_id ~ '^[a-z0-9][a-z0-9._@/-]{0,127}$'),
    email       VARCHAR      NOT NULL DEFAULT '',
    name        VARCHAR      NOT NULL DEFAULT '',
    PRIMARY KEY (user_id),
    UNIQUE (display_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ── 2. Index on display_id for lookups ───────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_user_info_display_id ON user_info(display_id);

-- ── 3. Populate user_info from existing users ─────────────────────────────────
-- display_id: lowercase email, replace chars outside [a-z0-9._@/-] with '-',
--             ensure starts with [a-z0-9], append row_num suffix for duplicates

INSERT INTO user_info (user_id, display_id, email, name)
SELECT
    user_id,
    CASE
        WHEN row_num = 1 THEN slugged
        ELSE SUBSTRING(slugged, 1, 124) || '-' || LPAD(CAST(row_num AS VARCHAR), 3, '0')
    END,
    email,
    name
FROM (
    SELECT
        user_id,
        email,
        name,
        slugged,
        ROW_NUMBER() OVER (
            PARTITION BY slugged
            ORDER BY created_at, user_id
        ) AS row_num
    FROM (
        SELECT
            user_id,
            email,
            name,
            created_at,
            SUBSTRING(
                REGEXP_REPLACE(
                    LOWER(email),
                    '[^a-z0-9._@/-]', '-', 'g'
                ), 1, 128
            ) AS slugged
        FROM users
    ) base
) u
ON CONFLICT DO NOTHING;
