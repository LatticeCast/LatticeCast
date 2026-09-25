-- upgrade
-- Password/App login is a central Lattice Cast session, not an OAuth client.
-- Keep client-scoped refresh families possible, while permitting central
-- refresh tokens to have no client_id.

ALTER TABLE private.sso_refresh_tokens
    ALTER COLUMN client_id DROP NOT NULL;

CREATE INDEX idx_sso_refresh_tokens_active_expiry
    ON private.sso_refresh_tokens (expires_at)
    WHERE revoked_at IS NULL;
