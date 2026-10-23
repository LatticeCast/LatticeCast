# SSO and Access

- LC is the first-party OAuth-style identity provider, so static/serverless
  apps need no separate auth backend. It issues local HS256 JWTs; middleware
  verifies only those JWTs—no external JWKS, userinfo, Google, or Authentik
  fallback.
- `auth.users`: UUID + application role. `gdpr.user_info`: handle/email/config.
  `gdpr.user_password`: bcrypt hash.
- `/login/password` and `/sso/token` issue the same access-token format.
  `services/lc_auth.py` owns access JWTs, opaque browser sessions, and hashed
  rotating refresh tokens.
- `/sso/authorize` is authorization-code + PKCE for registered clients.
  `/sso/handoff`, `/sso/launch`, and `/sso/browser-token` support registered
  public static/native clients. Redirect URI and origin are checked.
- Workspace access is separate from application role: `read`, `write`,
  `owner`. Higher levels materialize lower action rows. RLS uses
  `app.current_user_id`; owners manage the roster and the last owner remains.
- Controllers update membership stores only from confirmed API responses.
