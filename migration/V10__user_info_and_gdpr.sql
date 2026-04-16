-- upgrade
-- GDPR-aware split:
--   public.user_info   — public handle + display name (app CRUD)
--   auth.gdpr          — PII (email, legal name) — login_mgr only
--
-- Rationale: PII lives in its own schema so app role cannot read/leak it.
-- Right-to-be-forgotten: DELETE the gdpr row, user_info + users keep
-- foreign-key integrity for workspace data.

-- ── Ensure schemas exist (idempotent) ────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;

-- ── public.user_info — public handle only ──────────────────────────────────

CREATE TABLE IF NOT EXISTS user_info (
    user_id   UUID        NOT NULL,
    user_name VARCHAR(32) NOT NULL CHECK (
        user_name ~ '^[a-z0-9][a-z0-9_-]{2,31}$'
    ),
    PRIMARY KEY (user_id),
    UNIQUE (user_name),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_user_info_user_name ON user_info (user_name);

-- ── auth.gdpr — PII store (email, legal_name) ────────────────────────────────

CREATE TABLE IF NOT EXISTS auth.gdpr (
    user_id    UUID      NOT NULL,
    email      VARCHAR   NOT NULL,
    legal_name VARCHAR   NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id),
    UNIQUE (email),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_gdpr_email ON auth.gdpr (LOWER(email));

GRANT SELECT, INSERT, UPDATE, DELETE ON auth.gdpr TO login_mgr;

-- ── Populate from legacy users.email / users.name ───────────────────────────
-- user_name: slug from email; deduped with row_num suffix, clamped 3..32 char

INSERT INTO user_info (user_id, user_name)
SELECT
    user_id,
    CASE
        WHEN row_num = 1 THEN slug
        ELSE
            SUBSTRING(slug, 1, 28)
            || '-'
            || LPAD(CAST(row_num AS VARCHAR), 3, '0')
    END AS user_name
FROM (
    SELECT
        user_id,
        slug,
        ROW_NUMBER() OVER (
            PARTITION BY slug ORDER BY created_at, user_id
        ) AS row_num
    FROM (
        SELECT
            user_id,
            created_at,
            SUBSTRING(
                REGEXP_REPLACE(
                    LOWER(COALESCE(email, 'user')),
                    '[^a-z0-9_-]', '-', 'g'
                ), 1, 28
            ) AS slug
        FROM users
    ) AS base
) AS u
ON CONFLICT DO NOTHING;

INSERT INTO auth.gdpr (user_id, email, legal_name)
SELECT
    user_id,
    email,
    name
FROM users
WHERE email IS NOT NULL AND email <> ''
ON CONFLICT DO NOTHING;
