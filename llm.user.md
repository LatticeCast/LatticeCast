# LLM Context - User Management

> **Note:** For authentication architecture, see `llm.arch.auth.md`. For general project context, see `llm.md`.

## Login API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/login/google/token` | None | Exchange Google auth code for tokens |
| POST | `/api/login/authentik/token` | None | Exchange Authentik auth code for tokens |
| GET | `/api/login/me` | Bearer | Get current user info |

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
| GET | `/api/admin/users/{id}` | Get user by ID (email) |
| PUT | `/api/admin/users/{id}` | Update user role |
| DELETE | `/api/admin/users/{id}` | Delete user |

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
{"uuid": "xxx-xxx", "id": "user@example.com", "role": "user"}
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
uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid()
id          VARCHAR UNIQUE INDEX  -- email address
role        VARCHAR DEFAULT 'user' INDEX  -- 'user' | 'admin'
created_at  TIMESTAMP
updated_at  TIMESTAMP
```

## Seed Admin Users

Admin users are seeded via SQL migration:

```sql
-- migration/001_create_users.sql
INSERT INTO users (id, role) VALUES ('posetmage@gmail.com', 'admin') ON CONFLICT (id) DO NOTHING;
```
