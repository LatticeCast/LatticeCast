-- upgrade
-- Native handoff is wholly handled by Lattice Cast.  A client has one
-- database-owned default callback; the App never supplies a callback URL.

ALTER TABLE private.sso_client_redirect_uris
    ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT FALSE;

WITH first_redirect AS (
    SELECT DISTINCT ON (client_id)
           client_id,
           redirect_uri
    FROM private.sso_client_redirect_uris
    ORDER BY client_id, redirect_uri
)

UPDATE private.sso_client_redirect_uris AS redirect_data
SET    is_default = TRUE
FROM   first_redirect
WHERE  redirect_data.client_id = first_redirect.client_id
AND    redirect_data.redirect_uri = first_redirect.redirect_uri
AND    NOT EXISTS (
    SELECT 1
    FROM private.sso_client_redirect_uris AS existing_redirect
    WHERE existing_redirect.client_id = redirect_data.client_id
    AND   existing_redirect.is_default
);

CREATE UNIQUE INDEX sso_client_redirect_uris_one_default
    ON private.sso_client_redirect_uris (client_id)
    WHERE is_default;

ALTER TABLE private.sso_authorization_codes
    ADD COLUMN flow_type VARCHAR NOT NULL DEFAULT 'authorization_code'
    CHECK (flow_type IN ('authorization_code', 'native_launch', 'browser_exchange'));

CREATE INDEX idx_sso_authorization_codes_active_flow_expiry
    ON private.sso_authorization_codes (flow_type, expires_at)
    WHERE consumed_at IS NULL;
