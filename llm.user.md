# LLM Context - User Management

> **Note:** For authentication architecture, see `llm.arch.auth.md`. For general project context, see `llm.root.md`.

## Login API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/login/config` | None | App config (auth_required flag) |
| POST | `/api/v1/login/{provider}/token` | None | Exchange OAuth code for tokens (provider: google \| authentik) |
| POST | `/api/v1/login/password` | None | `{user_name, password}` — dev mode returns user UUID as access_token; AUTH_REQUIRED=true returns 501 |
| GET | `/api/v1/login/me` | Bearer | Get current user info (includes user_id, user_name, config) |
| PATCH | `/api/v1/login/me/config` | Bearer | Shallow-merge patch into caller's `gdpr.user_info.config`; null value removes key |
| PUT | `/api/v1/login/me/email` | Bearer | Update caller's email in `gdpr.user_info` (enforces uniqueness) |

### App Config

```bash
GET /api/v1/login/config

# Response
{"auth_required": true}
```

### Token Exchange Request/Response

```python
# Request
POST /api/v1/login/{provider}/token
{
    "code": "auth_code_from_redirect",
    "redirect_uri": "https://lattice-cast.posetmage.com/callback/google",
    "code_verifier": "pkce_verifier_43_to_128_chars"
}

# Response
{
    "access_token": "ya29.xxx",
    "refresh_token": "1//xxx",
    "id_token": "eyJ...",
    "expires_in": 3600,
    "userinfo": {
        "sub": "114068399299721366801",
        "email": "user@gmail.com",
        "name": "User Name",
        "picture": "https://..."
    }
}
```

### Get Current User (`/me`)

```bash
curl -X GET https://lattice-cast.posetmage.com/api/v1/login/me \
  -H "Authorization: Bearer $TOKEN"

# Response (MeResponse — v40: email/user_name/config from gdpr.user_info)
{
    "user_id": "00000000-0000-0000-0000-000000000000",
    "sub": "114068399299721366801",
    "email": "user@gmail.com",
    "name": "User Name",
    "picture": "https://...",
    "provider": "google",
    "role": "user",
    "user_name": "user-name",
    "config": {}
}
```

### Patch User Config (`/me/config`)

```bash
# Shallow-merge: null value removes a key
curl -X PATCH https://lattice-cast.posetmage.com/api/v1/login/me/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"darkMode": true, "lastView": null}'

# Response — full config blob after merge
{"darkMode": true}
```

### Update User Email (`/me/email`)

```bash
curl -X PUT https://lattice-cast.posetmage.com/api/v1/login/me/email \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "new@example.com"}'

# Response — full MeResponse with updated email
```

## Admin API Endpoints

All endpoints require `admin` role. Path param is `{user_email}` (looked up via `gdpr.user_info.email`, case-insensitive).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/users` | Create user (bootstraps auth.users + gdpr.user_info + workspace) |
| GET | `/api/v1/admin/users` | List users (paginated) |
| GET | `/api/v1/admin/users/{user_email}` | Get user by email |
| PUT | `/api/v1/admin/users/{user_email}` | Update user role |
| DELETE | `/api/v1/admin/users/{user_email}` | Delete user (cascades to gdpr.user_info, workspace_members) |

### Create User

```bash
TOKEN="ya29.xxx..."

curl -X POST https://lattice-cast.posetmage.com/api/v1/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "role": "user"}'

# Optional: supply user_name handle; auto-slugged from email if omitted
# -d '{"email": "user@example.com", "role": "user", "user_name": "myhandle"}'

# Response (201 — UserResponse)
{
    "user_id": "00000000-0000-0000-0000-000000000000",
    "email": "user@example.com",
    "role": "user",
    "user_name": "user",
    "config": {}
}
```

### List Users

```bash
curl -X GET "https://lattice-cast.posetmage.com/api/v1/admin/users?offset=0&limit=100" \
  -H "Authorization: Bearer $TOKEN"

# Response
{
    "users": [
        {
            "user_id": "00000000-0000-0000-0000-000000000000",
            "email": "user@example.com",
            "role": "user",
            "user_name": "user",
            "config": {}
        }
    ],
    "total": 1,
    "offset": 0,
    "limit": 100
}
```

### Update User Role

```bash
curl -X PUT https://lattice-cast.posetmage.com/api/v1/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

### Delete User

```bash
curl -X DELETE https://lattice-cast.posetmage.com/api/v1/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN"
# → 204 No Content
```

## Roles

| Role | Description |
|------|-------------|
| `user` | Standard user (can use app features) |
| `admin` | Administrator (can manage users) |

## Database Schema (v40)

```sql
-- auth.users (app readable, mgr-writable)
auth.users (
    user_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role       VARCHAR NOT NULL DEFAULT 'user',  -- 'user' | 'admin'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
)

-- gdpr.user_info (v40: PII + handle + config merged into one table)
-- Replaces the old auth.gdpr + public.user_info split.
-- app role: SELECT + UPDATE own row (RLS: user_id = current_user_id)
-- mgr role: full CRUD (BYPASSRLS)
-- A GDPR purge drops this row without touching auth.users or workspaces.
gdpr.user_info (
    user_id    UUID PRIMARY KEY REFERENCES auth.users(user_id),
    email      VARCHAR UNIQUE NOT NULL,
    user_name  VARCHAR UNIQUE NOT NULL,          -- URL-safe slug auto-derived from email
    config     JSONB NOT NULL DEFAULT '{}'       -- per-user UI config (darkMode, lastView, …)
)
```

**Key v40 changes vs prior schema:**
- `auth.gdpr` (email + legal_name) is gone.
- `public.user_info` (user_name only) is gone.
- Both merged into `gdpr.user_info` (email + user_name + config).
- `config` JSONB field stores per-user UI state; patched via `PATCH /login/me/config`.

## Auto-created Workspace

When a user is created (via admin API or `bootstrap_user` on first login), a default workspace is automatically created:

- `workspace_id` = fresh UUID
- `workspace_name` = user's **email** (not user_name)
- User is added to `workspace_members` with `role = 'owner'`

## Admin User Setup

Admin users are created via the admin API or directly in the database. No seed data is included in migrations.
