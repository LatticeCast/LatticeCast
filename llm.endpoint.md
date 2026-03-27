# LLM Context - API Endpoints

> **Note:** For authentication endpoints, see `llm.user.md`. For storage endpoints, see `llm.storage.md`. For general project context, see `llm.root.md`.

## OpenAPI Documentation

| Path | Description |
|------|-------------|
| `/docs` | Swagger UI (interactive) |
| `/redoc` | ReDoc UI (readable) |
| `/openapi.json` | OpenAPI 3.x JSON spec |

## Health & Debug

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/status` | None | Valkey & DB health check |
| GET | `/api/settings` | None | Current settings (non-sensitive) |
| GET | `/api/run-task/{seconds}` | None | Blocking task executor (debug) |
| GET | `/api/openapi-export` | None | Export OpenAPI spec to file |

## Authentication

See `llm.user.md` for full details.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/login/config` | None | App config (auth_required flag) |
| POST | `/api/login/{provider}/token` | None | Exchange OAuth code for tokens |
| GET | `/api/login/me` | Bearer | Get current user info |

## Tables

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/tables` | User | Create new table |
| GET | `/api/tables` | User | List user's tables |
| GET | `/api/tables/{table_id}` | User | Get table by ID |
| PUT | `/api/tables/{table_id}` | User | Update table name |
| DELETE | `/api/tables/{table_id}` | User | Delete table |

### Table Request/Response Examples

```python
# Create table
POST /api/tables
Authorization: Bearer {token}
Content-Type: application/json
{"name": "My Project"}

# Response (201)
{"id": "uuid", "user_id": "user@example.com", "name": "My Project", "created_at": "...", "updated_at": "..."}

# List tables
GET /api/tables
Authorization: Bearer {token}

# Response
[{"id": "uuid", "user_id": "user@example.com", "name": "My Project", ...}]
```

## Columns

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tables/{table_id}/columns` | User | List columns for table |
| POST | `/api/tables/{table_id}/columns` | User | Create column |
| PUT | `/api/columns/{column_id}` | User | Update column |
| DELETE | `/api/columns/{column_id}` | User | Delete column |

### Column Request/Response Examples

```python
# Create column
POST /api/tables/{table_id}/columns
Authorization: Bearer {token}
Content-Type: application/json
{"name": "Status", "type": "select", "options": {"choices": [{"value": "todo"}, {"value": "done"}]}, "position": 0}

# Response (201)
{"id": "uuid", "table_id": "uuid", "name": "Status", "type": "select", "options": {...}, "position": 0, "created_at": "..."}
```

### Column Types

| Type | JSONB Value | Example |
|------|-------------|---------|
| `text` | string | `"hello world"` |
| `number` | number | `42` |
| `date` | string (ISO) | `"2026-03-20"` |
| `select` | string | `"todo"` |
| `checkbox` | boolean | `true` |
| `url` | string | `"https://..."` |

## Rows

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/tables/{table_id}/rows` | User | Create row |
| GET | `/api/tables/{table_id}/rows` | User | List rows (paginated) |
| PUT | `/api/rows/{row_id}` | User | Update row data |
| DELETE | `/api/rows/{row_id}` | User | Delete row |

### Row Request/Response Examples

```python
# Create row
POST /api/tables/{table_id}/rows
Authorization: Bearer {token}
Content-Type: application/json
{"data": {"col_uuid_1": "value", "col_uuid_2": 42}}

# Response (201)
{"id": "uuid", "table_id": "uuid", "data": {"col_uuid_1": "value", "col_uuid_2": 42}, "created_at": "...", "updated_at": "..."}

# List rows (paginated)
GET /api/tables/{table_id}/rows?offset=0&limit=100
Authorization: Bearer {token}
```

## Storage (S3-compatible)

User files are prefixed with UUID (first 20 chars, no dashes).
- User sees: `/my-folder/file.txt`
- Stored as: `{uuid_prefix}/my-folder/file.txt`
- Admin sees full paths

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/storage/files` | User | List user's files |
| GET | `/api/storage/file/{path}` | User | Download file |
| PUT | `/api/storage/file/{path}` | User | Upload file (multipart) |
| DELETE | `/api/storage/file/{path}` | User | Delete file |
| GET | `/api/storage/admin/files` | Admin | List all files (full paths) |

### Storage Request/Response Examples

```python
# Upload file
PUT /api/storage/file/my-folder/data.json
Content-Type: multipart/form-data
Authorization: Bearer {token}

# Response
{"key": "my-folder/data.json", "size": 1234}

# List files
GET /api/storage/files?prefix=my-folder&max_keys=100
Authorization: Bearer {token}

# Response
{
  "files": [
    {"key": "my-folder/data.json", "size": 1234, "last_modified": "2024-01-01T00:00:00"}
  ],
  "prefix": "my-folder",
  "truncated": false
}
```

## Admin - User Management

Requires `admin` role. See `llm.user.md` for details.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/users` | Create user |
| GET | `/api/admin/users` | List users (paginated) |
| GET | `/api/admin/users/{user_id}` | Get user by ID (email) |
| PUT | `/api/admin/users/{user_id}` | Update user role |
| DELETE | `/api/admin/users/{user_id}` | Delete user |

### Admin Request/Response Examples

```python
# Create user
POST /api/admin/users
Authorization: Bearer {admin_token}
Content-Type: application/json
{"id": "user@example.com", "role": "user"}

# Response (201)
{"user_id": "user@example.com", "name": "", "role": "user"}

# List users
GET /api/admin/users?offset=0&limit=100
Authorization: Bearer {admin_token}

# Response
{
  "users": [{"user_id": "user@example.com", "name": "", "role": "user"}],
  "total": 1,
  "offset": 0,
  "limit": 100
}

# Update user
PUT /api/admin/users/user@example.com
Authorization: Bearer {admin_token}
Content-Type: application/json
{"role": "admin"}
```

## Error Responses

All endpoints return standard error format:

```json
{"detail": "Error message here"}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (not registered / wrong role) |
| 404 | Not found |
| 409 | Conflict (e.g., user already exists) |
| 500 | Internal server error |

## Adding Auth to Endpoints

```python
from fastapi import Depends
from middleware.auth import get_current_user, require_admin, require_user
from models.user import User

# Any registered user
@router.get("/endpoint")
async def endpoint(user: User = Depends(get_current_user)):
    return {"email": user.user_id}

# Admin only
@router.post("/admin-endpoint")
async def admin_endpoint(user: User = Depends(require_admin)):
    return {"admin": user.user_id}

# Subscribed users only (role = "user")
@router.get("/premium")
async def premium(user: User = Depends(require_user)):
    return {"subscriber": user.user_id}
```
