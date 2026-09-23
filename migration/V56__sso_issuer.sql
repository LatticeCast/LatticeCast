-- upgrade
-- Lattice Cast is the central issuer for first-party App and m-* clients.
-- These are durable authentication records, deliberately NOT UNLOGGED: losing
-- all active sessions or one-time grants after a crash is not acceptable.

CREATE TABLE IF NOT EXISTS private.sso_clients (
    client_id          VARCHAR PRIMARY KEY,
    client_kind        VARCHAR NOT NULL CHECK (client_kind IN ('public', 'confidential')),
    client_secret_hash VARCHAR,
    display_name       VARCHAR NOT NULL,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at         TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CHECK (
        (client_kind = 'public' AND client_secret_hash IS NULL)
        OR (client_kind = 'confidential' AND client_secret_hash IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS private.sso_client_redirect_uris (
    client_id    VARCHAR NOT NULL REFERENCES private.sso_clients (client_id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL CHECK (POSITION('#' IN redirect_uri) = 0),
    PRIMARY KEY (client_id, redirect_uri)
);

CREATE TABLE IF NOT EXISTS private.sso_sessions (
    session_id         UUID PRIMARY KEY DEFAULT GEN_RANDOM_UUID(),
    session_token_hash VARCHAR NOT NULL UNIQUE,
    user_id            UUID NOT NULL REFERENCES gdpr.user_info (user_id) ON DELETE CASCADE,
    auth_method        VARCHAR NOT NULL,
    created_at         TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    last_seen_at       TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    expires_at         TIMESTAMP NOT NULL,
    revoked_at         TIMESTAMP,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_sso_sessions_active_user
    ON private.sso_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS private.sso_authorization_codes (
    code_hash             VARCHAR PRIMARY KEY,
    client_id             VARCHAR NOT NULL REFERENCES private.sso_clients (client_id) ON DELETE CASCADE,
    user_id               UUID NOT NULL REFERENCES gdpr.user_info (user_id) ON DELETE CASCADE,
    session_id            UUID REFERENCES private.sso_sessions (session_id) ON DELETE SET NULL,
    redirect_uri          TEXT NOT NULL,
    code_challenge        VARCHAR,
    code_challenge_method VARCHAR CHECK (code_challenge_method IS NULL OR code_challenge_method = 'S256'),
    issued_at             TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    expires_at            TIMESTAMP NOT NULL,
    consumed_at           TIMESTAMP,
    CHECK (expires_at > issued_at),
    CHECK (
        (code_challenge IS NULL AND code_challenge_method IS NULL)
        OR (code_challenge IS NOT NULL AND code_challenge_method = 'S256')
    )
);

CREATE INDEX IF NOT EXISTS idx_sso_authorization_codes_active_expiry
    ON private.sso_authorization_codes (expires_at)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS private.sso_refresh_tokens (
    token_hash  VARCHAR PRIMARY KEY,
    family_id   UUID NOT NULL,
    client_id   VARCHAR NOT NULL REFERENCES private.sso_clients (client_id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES gdpr.user_info (user_id) ON DELETE CASCADE,
    session_id  UUID REFERENCES private.sso_sessions (session_id) ON DELETE SET NULL,
    issued_at   TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    expires_at  TIMESTAMP NOT NULL,
    revoked_at  TIMESTAMP,
    replaced_at TIMESTAMP,
    CHECK (expires_at > issued_at)
);

REVOKE ALL ON TABLE private.sso_clients, private.sso_client_redirect_uris,
    private.sso_sessions, private.sso_authorization_codes,
    private.sso_refresh_tokens FROM public, app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE private.sso_clients,
    private.sso_client_redirect_uris, private.sso_sessions,
    private.sso_authorization_codes, private.sso_refresh_tokens TO mgr;
