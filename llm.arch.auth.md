# LatticeCast — Authentication Architecture

LatticeCast accepts password-login JWTs and OAuth credentials from Google or
Authentik. Authentication resolves a token; PostgreSQL RLS authorizes access to
workspace data.

## Request Flow

```text
Authorization: Bearer <token>
  -> middleware/token.py verifies local JWT, Authentik JWT, or Google token
  -> middleware/auth.py resolves a registered auth.users identity
  -> get_rls_session sets app.current_user_id
  -> PostgreSQL policies filter/permit data
```

Users are not auto-created during token verification. Bootstrap and admin user
creation are explicit flows.

## Credentials and Identity

- `auth.users` contains UUID identity and application role (`user`/`admin`).
- `gdpr.user_info` contains email, unique `user_name`, and user config.
- `gdpr.user_password` contains an optional bcrypt hash and is accessible only
  through the login/admin database role.
- Password login resolves `user_name` or email and issues a locally signed JWT.
  Existing accounts without a password row use the repository's bootstrap
  behavior; inspect `router/api/auth.py` before changing it.
- Google and Authentik use PKCE flows coordinated by the frontend auth modules.

## Two Database Engines

| Engine | Role | Use |
|---|---|---|
| `app_engine` | `app_user` | Normal API work with RLS |
| `login_engine` | `mgr_user` | Login/admin operations with `BYPASSRLS` |

Engine setup is in `backend/src/core/db.py`. Keep normal domain routes on the
RLS engine; do not use the manager engine to bypass workspace authorization.

## Backend Entry Points

| File | Responsibility |
|---|---|
| `backend/src/middleware/token.py` | Bearer verification across providers |
| `backend/src/middleware/auth.py` | User resolution, role gates, RLS session |
| `backend/src/middleware/jwks.py` | Authentik JWKS retrieval and PG caching |
| `backend/src/router/api/auth.py` | Login and self-service endpoints |
| `backend/src/router/api/admin/users.py` | Admin user lifecycle |
| `backend/src/repository/user.py` | Identity/PII/password persistence |
| `backend/src/util/security.py` | Password hashing and verification |

## Frontend Entry Points

| File | Responsibility |
|---|---|
| `frontend/src/lib/stores/auth.store.ts` | Persisted login state |
| `frontend/src/lib/auth/auth.service.ts` | Login orchestration |
| `frontend/src/lib/auth/pkce.ts` | PKCE verifier/challenge |
| `frontend/src/lib/auth/providers/` | Provider-specific configuration |
| `frontend/src/lib/backend/auth.ts` | Auth/current-user controller |
| `frontend/src/routes/+layout.ts` | Central route auth gate |

## Configuration and Gotchas

Relevant settings are defined in `.env.example` and
`backend/src/config/settings.py`: JWT secret/lifetime, provider client settings,
and manager DB credentials. Vite exposes only selected provider configuration.

- Application admin role and workspace owner level are different concepts.
- A valid external token still fails if no registered local user resolves.
- Clear/reset auth-dependent stores on logout.
- Never expose password hashes through `gdpr.user_info` or the app engine.
