# LLM Context - User Management

> **Note:** For authentication architecture, see `llm.arch.auth.md`. For general project context, see `llm.root.md`.

## Login API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/login/config` | None | App config (auth_required flag) |
| POST | `/api/login/google/token` | None | Exchange Google auth code for tokens |
| POST | `/api/login/authentik/token` | None | Exchange Authentik auth code for tokens |
| GET | `/api/login/me` | Bearer | Get current user info |

### App Config

```bash
GET /api/login/config

# Response
{"auth_required": true}
```

### Token Exchange Request/Response

```python
# Request
POST /api/login/{provider}/token
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
curl -X GET https://lattice-cast.posetmage.com/api/login/me \
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
| POST | `/api/admin/users` | Create user |
| GET | `/api/admin/users` | List users (paginated) |
| GET | `/api/admin/users/{user_id}` | Get user by ID (email) |
| PUT | `/api/admin/users/{user_id}` | Update user role |
| DELETE | `/api/admin/users/{user_id}` | Delete user |

## Add User via curl

```bash
# Get admin token from Debug page after login
TOKEN="ya29.xxx..."

# Add user
curl -X POST https://lattice-cast.posetmage.com/api/admin/users \
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
curl -X GET "https://lattice-cast.posetmage.com/api/admin/users?offset=0&limit=100" \
  -H "Authorization: Bearer $TOKEN"
```

## Update User Role

```bash
curl -X PUT https://lattice-cast.posetmage.com/api/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

## Delete User

```bash
curl -X DELETE https://lattice-cast.posetmage.com/api/admin/users/user@example.com \
  -H "Authorization: Bearer $TOKEN"
```

## Database Schema

```sql
-- users table
user_id     VARCHAR PRIMARY KEY  -- email address
name        VARCHAR NOT NULL DEFAULT ''
role        VARCHAR NOT NULL DEFAULT 'user'  -- 'user' | 'admin'
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()
```

## Admin User Setup

Admin users are created via the admin API or directly in the database. No seed data is included in migrations.
