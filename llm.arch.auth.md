# LLM Context — Authentication Architecture

## Overview

Dual OAuth (Google + Authentik) with PKCE. `AUTH_REQUIRED=false` dev mode bypasses OAuth — Bearer token treated as user_id directly. Two PG engines: `app_engine` (RLS) and `login_engine` (`mgr_user`, BYPASSRLS).

## Backend Auth Files

| File | Purpose |
|------|---------|
| `middleware/token.py` | `verify_bearer_token()` — Authentik JWT → Google userinfo → 401 |
| `middleware/auth.py` | `get_current_user`, `get_rls_session`, `require_admin`, `require_user` |
| `middleware/jwks.py` | JWKS fetch + Valkey cache (`jwks:{provider}`, TTL 3600s) |
| `router/api/auth.py` | `/login/*` endpoints (OAuth exchange, password, me, config, email) |
| `config/settings.py` | `DatabaseSettings.app_async_url` / `login_async_url`, OAuth config |

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
2. `AUTH_REQUIRED=false`: return `{"user_id": token, "_provider": "none"}`
3. Try Authentik JWT (RS256 via JWKS, validate audience + issuer)
4. Fallback: Google userinfo endpoint (opaque token)
5. Attach `_provider` field; raise 401 if all fail

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
| GET | `/config` | No | `{ auth_required: bool }` |
| POST | `/password` | No | Dev-mode login (501 when `AUTH_REQUIRED=true`) |
| POST | `/{provider}/token` | No | OAuth code exchange (google, authentik) |
| GET | `/me` | Yes | Current user info + config (uses RLS session) |
| PATCH | `/me/config` | Yes | Shallow-merge keys into `user_info.config` (null removes key) |
| PUT | `/me/email` | Yes | Update email (uniqueness enforced, uses login_session) |

## Database Schema

```sql
-- V2: auth.users (identity only)
auth.users (user_id UUID PK, role VARCHAR DEFAULT 'user', created_at, updated_at)

-- V3: gdpr.user_info (PII + handle + config)
gdpr.user_info (user_id UUID PK FK→auth.users CASCADE, email UNIQUE, user_name VARCHAR(32) UNIQUE, config JSONB)
-- user_name CHECK: ^[a-z0-9][a-z0-9_-]{2,31}$
```

GDPR purge: drop `gdpr.user_info` row — `auth.users` and audit trails remain.

## Environment Variables

```bash
AUTH_REQUIRED=true             # false = dev mode (token = user_id, password login enabled)
GOOGLE_CLIENT_ID=xxx           # Google OAuth
GOOGLE_CLIENT_SECRET=xxx
AUTHENTIK_URL=https://...      # Authentik OAuth
AUTHENTIK_CLIENT_ID=xxx
POSTGRES_MGR_PASSWORD=mgr_pws  # mgr_user password (login_engine)
```

`vite.config.ts` maps env vars to `VITE_*` at build time.
