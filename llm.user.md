# LLM Context - User Management

> **Note:** For authentication architecture, see `llm.arch.auth.md`. For general project context, see `llm.root.md`.

## Login API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/login/config` | None | App config (auth_required flag) |
| POST | `/api/v1/login/google/token` | None | Exchange Google auth code for tokens |
| POST | `/api/v1/login/authentik/token` | None | Exchange Authentik auth code for tokens |
| GET | `/api/v1/login/me` | Bearer | Get current user info |

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

### Get Current User

```bash
curl -X GET https://lattice-cast.posetmage.com/api/v1/login/me \
  -H "Authorization: Bearer $TOKEN"

# Response
{
    "sub": "114068399299721366801",
    "email": "user@gmail.com",
    "name": "User Name",
    "picture": "https://...",
    "provider": "google",
    "role": "user"
}
```

## Admin API Endpoints

All endpoints require admin role (Bearer token from admin user).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/users` | Create user |
| GET | `/api/v1/admin/users` | List users (paginated) |
| GET | `/api/v1/admin/users/{user_id}` | Get user by user_id (UUID), user_name, or email |
| PUT | `/api/v1/admin/users/{user_id}` | Update user role |
| DELETE | `/api/v1/admin/users/{user_id}` | Delete user |

## Add User via curl

```bash
# Get admin token from Debug page after login
TOKEN="ya29.xxx..."

# Add user
curl -X POST https://lattice-cast.posetmage.com/api/v1/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "user@example.com", "role": "user"}'

# Response
{"user_id": "user@example.com", "name": "", "role": "user"}
```

## Roles

| Role | Description |
|------|-------------|
| `user` | Standard user (can use app features) |
| `admin` | Administrator (can manage users) |

## List Users

```bash
curl -X GET "https://lattice-cast.posetmage.com/api/v1/admin/users?offset=0&limit=100" \
  -H "Authorization: Bearer $TOKEN"
```

## Update User Role

```bash
curl -X PUT https://lattice-cast.posetmage.com/api/v1/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

## Delete User

```bash
curl -X DELETE https://lattice-cast.posetmage.com/api/v1/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN"
```

## Database Schema

```sql
-- auth.users (login_mgr-writable, app readable)
auth.users (
    user_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role        VARCHAR NOT NULL DEFAULT 'user',   -- 'user' | 'admin'
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
)

-- auth.gdpr (PII — login_mgr only, NOT exposed via app engine)
auth.gdpr (
    user_id     UUID PK FK auth.users,
    email       VARCHAR UNIQUE NOT NULL,
    legal_name  VARCHAR NOT NULL DEFAULT '',
    created_at  TIMESTAMP,
    updated_at  TIMESTAMP
)

-- public.user_info (public handle — visible to app role)
public.user_info (
    user_id     UUID PK FK auth.users,
    user_name   VARCHAR(32) UNIQUE NOT NULL    -- CHECK: ^[a-z0-9][a-z0-9_-]{2,31}$
)
```

## Auto-created Workspace

When a user is created (via admin API or `get_or_create` on first login), a default workspace is automatically created:
- `workspace_id` = fresh UUID
- `workspace_name` = user's `user_name`
- User is added to `workspace_members` with `role = 'owner'`

## Admin User Setup

Admin users are created via the admin API or directly in the database. No seed data is included in migrations.
