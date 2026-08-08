# LLM Context - User Management

> See `llm.arch.auth.md` for auth architecture, `llm.root.md` for project context.

## Login API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/login/{provider}/token` | None | Exchange OAuth code for tokens (provider: google \| authentik) |
| POST | `/api/v1/login/password` | None | `{user_name, password}` — self-signed JWT; password only checked if `gdpr.user_password` has a row |
| GET | `/api/v1/login/me` | Bearer | Current user info (user_id, user_name, config, role) |
| PATCH | `/api/v1/login/me/config` | Bearer | Shallow-merge patch into `gdpr.user_info.config`; null removes key |
| PUT | `/api/v1/login/me/email` | Bearer | Update caller's email (enforces uniqueness) |
| PUT | `/api/v1/login/me/password` | Bearer | `{new_password, current_password?}` — set/change password |

### Password Login

```bash
POST /api/v1/login/password
{"user_name": "handle-or-email", "password": "unchecked-unless-a-password-is-set"}
# Resolves by user_name first, then email.
# No row in gdpr.user_password → password ignored, JWT issued directly.
# Row exists → password must match the bcrypt hash, else 401.
# Response: TokenResponse with access_token = self-signed JWT (see llm.arch.auth.md)
```

### Token Exchange

```bash
POST /api/v1/login/{provider}/token
{"code": "auth_code", "redirect_uri": "https://…/callback/google", "code_verifier": "pkce_43_to_128"}
# Response: {access_token, refresh_token?, id_token?, expires_in?, userinfo: {sub, email, name?, picture?}}
```

### Get Current User (`/me`)

```bash
GET /api/v1/login/me   # Authorization: Bearer $TOKEN
# Response (MeResponse — email/user_name/config from gdpr.user_info)
{"user_id": "uuid", "sub": "…", "email": "…", "name": "…", "picture": "…",
 "provider": "google|authentik|none", "role": "user|admin", "user_name": "…", "config": {}}
```

### Patch Config / Update Email

```bash
PATCH /api/v1/login/me/config   # body: {"darkMode": true, "lastView": null}  → returns merged config
PUT   /api/v1/login/me/email    # body: {"email": "new@example.com"}          → returns MeResponse
```

## Admin API Endpoints

All require `admin` role. Path param `{user_email}` looked up case-insensitive via `gdpr.user_info.email`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/users` | Create user (bootstraps auth.users + gdpr.user_info + workspace) |
| GET | `/api/v1/admin/users` | List users (paginated, `?offset=0&limit=100`) |
| GET | `/api/v1/admin/users/{user_email}` | Get user by email |
| PUT | `/api/v1/admin/users/{user_email}` | Update user role |
| DELETE | `/api/v1/admin/users/{user_email}` | Delete user (cascades to gdpr.user_info, workspace_members) |

Create: `POST {"email":"…","role":"user","user_name":"optional"}` → 201 UserResponse. user_name auto-slugged from email if omitted.

## Roles

**PG roles:** `mgr` (group, BYPASSRLS, full DML all schemas) → `mgr_user` (login, used by login_session). `app` (group, RLS, DML public + SELECT auth) → `app_user` (login, used by app_session).

**App roles:** `user` (standard) | `admin` (manages users via `/admin/users/*`).

## Database Schema

```sql
-- auth.users — identity core (V2__users.sql)
-- app: SELECT; mgr: full CRUD
auth.users (
    user_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role       VARCHAR NOT NULL DEFAULT 'user',  -- 'user' | 'admin'
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
)

-- gdpr.user_info — PII + handle + config (V3__user_info.sql)
-- Replaces old auth.gdpr + public.user_info split.
-- app: SELECT/UPDATE own row (RLS user_id = current_user_id)
-- mgr: full CRUD (BYPASSRLS)
-- GDPR purge: drop this row without touching auth.users or workspaces.
gdpr.user_info (
    user_id   UUID PRIMARY KEY REFERENCES auth.users(user_id) ON DELETE CASCADE,
    email     VARCHAR UNIQUE NOT NULL,
    user_name VARCHAR(32) UNIQUE NOT NULL,       -- CHECK: ^[a-z0-9][a-z0-9_-]{2,31}$
    config    JSONB NOT NULL DEFAULT '{}'        -- per-user UI config (darkMode, lastView, …)
)
```

## Auto-created Workspace

`bootstrap_user` (admin create/bootstrap path) creates:

- `workspace_id` = fresh UUID (`default_factory=uuid4`)
- `workspace_name` = user's **email** (not user_name)
- three `workspace_members` rows: `read`, `write`, and `owner`

## Workspace Access Levels

The API presents one `level`, but V33 stores one row per granted action:

| Level | Stored actions | Effective access |
|-------|----------------|------------------|
| `read` | read | View workspace/table/row/view data |
| `write` | read + write | Read plus mutate tables, rows, and views |
| `owner` | read + write + owner | Write plus workspace/member administration |

Member list responses aggregate action rows back to the highest level.
