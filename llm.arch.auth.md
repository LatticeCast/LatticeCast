# LLM Context — Authentication Architecture

## Overview

Dual OAuth (Google + Authentik) with PKCE, plus a password-login flow that
issues a self-signed JWT. Per-account `gdpr.user_password` (1:1 with
`user_info`, no grants to `app` — see Database Schema) decides whether
`POST /login/password` checks the password: no row skips verification
and issues a JWT directly, a row → password must match (bcrypt,
`util/security.py`). Two PG engines: `app_engine` (RLS) and `login_engine`
(`mgr_user`, BYPASSRLS).

## Backend Auth Files

| File | Purpose |
|------|---------|
| `middleware/token.py` | `verify_bearer_token()` — local JWT → Authentik JWT → Google userinfo → 401 |
| `middleware/auth.py` | `get_current_user`, `get_rls_session`, `require_admin`, `require_user` |
| `middleware/jwks.py` | JWKS fetch + PG cache (`{provider}:jwks`, TTL 3600s) |
| `router/api/auth.py` | `/login/*` endpoints (OAuth exchange, password, me, email) |
| `util/security.py` | `hash_password` / `verify_password` (bcrypt via passlib) |
| `config/settings.py` | `DatabaseSettings.app_async_url` / `login_async_url`, `jwt_secret_key`, OAuth config |

## Frontend Auth Files

| File | Purpose |
|------|---------|
| `lib/stores/auth.store.ts` | Svelte writable store ↔ localStorage (`loginInfo` key) |
| `lib/auth/auth.service.ts` | Login flow orchestration |
| `lib/auth/pkce.ts` | PKCE verifier (128-char) + SHA256 challenge |
| `lib/auth/providers/` | google.ts, authentik.ts — provider-specific config |
| `lib/backend/auth.ts` | API client (fetchAppConfig, exchangeCodeViaBackend, fetchMe) |
| `routes/login/+page.svelte` | Login UI |
| `routes/callback/{provider}/` | OAuth callback pages (google, authentik) |

## Token Verification (`middleware/token.py`)

1. Extract Bearer token from `Authorization` header
2. Try our own JWT (HS256, `JWT_SECRET_KEY`, issued by `password_login`) → `_provider: "none"`
3. Try Authentik JWT (RS256 via JWKS, validate audience + issuer) → `_provider: "authentik"`
4. Fallback: Google userinfo endpoint (opaque token) → `_provider: "google"`
5. Raise 401 `"Token expired"` if any step's JWT was expired, else `"Invalid token"`

## User Resolution (`middleware/auth.py`)

`get_current_user` resolves token payload → `User`:
- `user_id` field (UUID or user_name) → `UserRepository.resolve_user()` via app session
- `email` field → `resolve_user_by_email()` via app session (queries `gdpr.user_info`)
- No auto-creation — admins must bootstrap users; raises 403 if not found

`get_rls_session`: sets `app.current_user_id` via `set_config()`. No manual reset — pool's `DISCARD ALL` on release clears it.

`require_admin` / `require_user`: role gate dependencies (403 on mismatch).

## Dual Engine Architecture (`core/db.py`)

| Engine | PG Role | search_path | Purpose |
|--------|---------|-------------|---------|
| `app_engine` | `app_user` | `public,auth,gdpr` | General API — CRUD on public, SELECT on auth |
| `login_engine` | `mgr_user` | `public,auth,gdpr` | Auth/admin — BYPASSRLS, CRUD everywhere |

`mgr_user` has `BYPASSRLS` (V15 grant) — needed at login time when no user is authenticated yet (RLS would return zero rows). Both engines include `gdpr` in search_path so unqualified `user_info` references resolve.

Env: `POSTGRES_MGR_PASSWORD` configures `mgr_user` password.

## API Endpoints (`/api/v1/login/`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/password` | No | Password login → self-signed JWT (no row in `user_password` = unchecked) |
| POST | `/{provider}/token` | No | OAuth code exchange (google, authentik) |
| GET | `/me` | Yes | Current user info + config (uses RLS session) |
| PATCH | `/me/config` | Yes | Shallow-merge keys into `user_info.config` (null removes key) |
| PUT | `/me/email` | Yes | Update email (uniqueness enforced, uses login_session) |
| PUT | `/me/password` | Yes | Set/change password (`current_password` required once one is set) |

## Database Schema

```sql
-- V2: auth.users (identity only)
auth.users (user_id UUID PK, role VARCHAR DEFAULT 'user', created_at, updated_at)

-- V3: gdpr.user_info (PII + handle + config)
gdpr.user_info (user_id UUID PK FK→auth.users CASCADE, email UNIQUE, user_name VARCHAR(32) UNIQUE, config JSONB)
-- user_name CHECK: ^[a-z0-9][a-z0-9_-]{2,31}$

-- V32: gdpr.user_password (optional password-login credential)
gdpr.user_password (user_id UUID PK FK→user_info CASCADE, password_hash VARCHAR, updated_at TIMESTAMP)
-- No grants to app at all — only mgr_user (login_session) touches it.
-- Kept off user_info because V20 grants app_user broad SELECT there
-- (needed to resolve other users by email/user_name for workspace
-- invites); a password_hash column on that table would leak through
-- every one of those reads. Self-only RLS too, as a second layer.
```

GDPR purge: drop `gdpr.user_info` row — cascades `gdpr.user_password`.
`auth.users` and audit trails remain.

## Environment Variables

```bash
JWT_SECRET_KEY=xxx             # signs self-issued JWTs (password-login flow)
JWT_EXPIRE_MINUTES=1440        # self-issued JWT lifetime (default 24h)
GOOGLE_CLIENT_ID=xxx           # Google OAuth
GOOGLE_CLIENT_SECRET=xxx
AUTHENTIK_URL=https://...      # Authentik OAuth
AUTHENTIK_CLIENT_ID=xxx
POSTGRES_MGR_PASSWORD=mgr_pws  # mgr_user password (login_engine)
```

`vite.config.ts` maps env vars to `VITE_*` at build time.
