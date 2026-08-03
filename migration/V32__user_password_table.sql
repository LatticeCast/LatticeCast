-- upgrade
-- Optional password for the password-login flow (see
-- router/api/auth.py::password_login). NULL / no row means the account
-- has no password set — password_login skips verification and issues a
-- JWT directly. A row means the supplied password must match the
-- bcrypt hash. This replaces the old global AUTH_REQUIRED=true/false
-- split with a single per-account setting.
--
-- Lives in its own table, not as a column on gdpr.user_info: V20 grants
-- app_user broad SELECT across gdpr.user_info (needed so the app can
-- resolve OTHER users by email/user_name when inviting workspace
-- members) — a password_hash column on that same table would ride
-- along with every one of those broad reads. gdpr.user_password gets
-- NO grants to app at all: only mgr_user (login_session, BYPASSRLS)
-- ever touches it, via password_login / set_me_password, both of which
-- already scope every lookup to the caller's own user_id.
--
-- FKs to gdpr.user_info (not auth.users) so a GDPR purge (drop the
-- user_info row) cascades the stored password hash too.

CREATE TABLE IF NOT EXISTS gdpr.user_password (
    user_id       UUID      NOT NULL,
    password_hash VARCHAR   NOT NULL,
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id),
    FOREIGN KEY (user_id) REFERENCES gdpr.user_info (user_id) ON DELETE CASCADE
);

GRANT SELECT, INSERT, UPDATE, DELETE ON gdpr.user_password TO mgr;

-- Self-only RLS, same shape as V10's user_info_self. Belt and braces:
-- app has no grants on this table at all today, and mgr is BYPASSRLS,
-- so this policy is a no-op right now — but it means a future grant to
-- app can never accidentally expose another user's password_hash.

ALTER TABLE gdpr.user_password ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_password_self ON gdpr.user_password;
CREATE POLICY user_password_self ON gdpr.user_password
USING (
    user_id = (nullif(current_setting('app.current_user_id', true), ''))::UUID
);
