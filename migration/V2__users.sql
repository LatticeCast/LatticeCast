-- upgrade
-- Identity table — minimal. user_id is the authoritative key; all PII
-- (email, user_name, profile) lives in gdpr.user_info so a GDPR purge
-- can drop the PII row while leaving the user_id intact in audit trails.

CREATE TABLE IF NOT EXISTS auth.users (
    user_id    UUID      NOT NULL DEFAULT gen_random_uuid(),
    role       VARCHAR   NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS ix_users_role ON auth.users (role);
