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
| GET | `/api/v1/status` | None | Valkey & DB health check |
| GET | `/api/v1/settings` | None | Current settings (non-sensitive) |
| GET | `/api/v1/run-task/{seconds}` | None | Blocking task executor (debug) |
| GET | `/api/v1/openapi-export` | None | Export OpenAPI spec to file |

## Authentication

See `llm.user.md` for full details.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/login/config` | None | App config (auth_required flag) |
| POST | `/api/v1/login/{provider}/token` | None | Exchange OAuth code for tokens |
| GET | `/api/v1/login/me` | Bearer | Get current user info |

## Workspaces

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/workspaces` | User | Create workspace |
| GET | `/api/v1/workspaces` | User | List user's workspaces |
| GET | `/api/v1/workspaces/{workspace_id}` | User | Get workspace |
| PUT | `/api/v1/workspaces/{workspace_id}` | Owner | Update workspace name |
| DELETE | `/api/v1/workspaces/{workspace_id}` | Owner | Delete workspace |
| POST | `/api/v1/workspaces/{workspace_id}/members` | Owner | Add member |
| DELETE | `/api/v1/workspaces/{workspace_id}/members/{user_id}` | Owner | Remove member |
| GET | `/api/v1/workspaces/{workspace_id}/members` | User | List members |

### Workspace Request/Response Examples

```python
# Create workspace
POST /api/v1/workspaces
Authorization: Bearer {token}
Content-Type: application/json
{"name": "My Workspace"}

# Response (201)
{"workspace_id": "...", "name": "My Workspace", "created_at": "...", "updated_at": "..."}

# List workspaces
GET /api/v1/workspaces
Authorization: Bearer {token}

# Response
[{"workspace_id": "user@example.com", "name": "user@example.com", ...}]

# Add member
POST /api/v1/workspaces/{workspace_id}/members
Authorization: Bearer {token}
Content-Type: application/json
{"user_id": "other@example.com", "role": "member"}
```

> **Note:** A default workspace (workspace_id = user email) is auto-created when a user registers.

## Tables

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/tables` | User | Create new table |
| GET | `/api/v1/tables` | User | List user's tables (all workspaces) |
| GET | `/api/v1/tables/{table_id}` | Member | Get table by ID |
| PUT | `/api/v1/tables/{table_id}` | Member | Update table name |
| DELETE | `/api/v1/tables/{table_id}` | Member | Delete table |
| GET | `/api/v1/tables/{table_id}/columns` | Member | List columns (from table.columns) |
| POST | `/api/v1/tables/{table_id}/columns` | Member | Add column |
| PUT | `/api/v1/tables/{table_id}/columns/{column_id}` | Member | Update column |
| DELETE | `/api/v1/tables/{table_id}/columns/{column_id}` | Member | Delete column |
| GET | `/api/v1/tables/{table_id}/views` | Member | List views |
| POST | `/api/v1/tables/{table_id}/views` | Member | Create view |
| PUT | `/api/v1/tables/{table_id}/views/{view_name}` | Member | Update view config |
| DELETE | `/api/v1/tables/{table_id}/views/{view_name}` | Member | Delete view |
| POST | `/api/v1/tables/template/pm` | User | Create PM template table |

## Rows

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/tables/{table_id}/rows` | Member | Create row (row_number auto-set by trigger) |
| GET | `/api/v1/tables/{table_id}/rows` | Member | List rows (paginated) |
| PUT | `/api/v1/tables/{table_id}/rows/{row_number}` | Member | Update row data |
| DELETE | `/api/v1/tables/{table_id}/rows/{row_number}` | Member | Delete row |
| GET | `/api/v1/tables/{table_id}/rows/{row_number}/doc` | Member | Get ticket doc (markdown from MinIO) |
| PUT | `/api/v1/tables/{table_id}/rows/{row_number}/doc` | Member | Save ticket doc (markdown to MinIO) |

### Table Request/Response Examples

```python
# Create table
POST /api/v1/tables
Authorization: Bearer {token}
Content-Type: application/json
{"name": "My Project", "workspace_id": "user@example.com"}

# Response (201)
{"table_id": "uuid", "workspace_id": "user@example.com", "name": "My Project", "columns": [], "created_at": "...", "updated_at": "..."}

# List tables
GET /api/v1/tables
Authorization: Bearer {token}

# Response
[{"table_id": "uuid", "workspace_id": "user@example.com", "name": "My Project", "columns": [...], ...}]
```

### Column Request/Response Examples

```python
# Add column
POST /api/v1/tables/{table_id}/columns
Authorization: Bearer {token}
Content-Type: application/json
{"name": "Status", "type": "select", "options": {"choices": [{"value": "todo", "color": "..."}, {"value": "done", "color": "..."}]}, "position": 0}

# Response (201)
{"id": "uuid", "table_id": "uuid", "name": "Status", "type": "select", "options": {...}, "position": 0, "created_at": "..."}
```

> **Note:** Columns are stored in `tables.columns` JSONB — there is no separate `columns` SQL table.

### Column Types

| Type | JSONB Value | Example |
|------|-------------|---------|
| `text` | string | `"hello world"` |
| `number` | number | `42` |
| `date` | string (ISO) | `"2026-03-20"` |
| `select` | string | `"todo"` |
| `tags` | array of strings | `["tag1", "tag2"]` |
| `checkbox` | boolean | `true` |
| `url` | string | `"https://..."` |

## Storage (S3-compatible)

User files are prefixed with UUID (first 20 chars, no dashes).
- User sees: `/my-folder/file.txt`
- Stored as: `{uuid_prefix}/my-folder/file.txt`
- Admin sees full paths

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/storage/files` | User | List user's files |
| GET | `/api/v1/storage/file/{path}` | User | Download file |
| PUT | `/api/v1/storage/file/{path}` | User | Upload file (multipart) |
| DELETE | `/api/v1/storage/file/{path}` | User | Delete file |
| GET | `/api/v1/storage/admin/files` | Admin | List all files (full paths) |

### Storage Request/Response Examples

```python
# Upload file
PUT /api/v1/storage/file/my-folder/data.json
Content-Type: multipart/form-data
Authorization: Bearer {token}

# Response
{"key": "my-folder/data.json", "size": 1234}

# List files
GET /api/v1/storage/files?prefix=my-folder&max_keys=100
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
| POST | `/api/v1/admin/users` | Create user |
| GET | `/api/v1/admin/users` | List users (paginated) |
| GET | `/api/v1/admin/users/{user_id}` | Get user by ID (email) |
| PUT | `/api/v1/admin/users/{user_id}` | Update user role |
| DELETE | `/api/v1/admin/users/{user_id}` | Delete user |

### Admin Request/Response Examples

```python
# Create user
POST /api/v1/admin/users
Authorization: Bearer {admin_token}
Content-Type: application/json
{"id": "user@example.com", "role": "user"}

# Response (201)
{"user_id": "user@example.com", "name": "", "role": "user"}

# List users
GET /api/v1/admin/users?offset=0&limit=100
Authorization: Bearer {admin_token}

# Response
{
  "users": [{"user_id": "user@example.com", "name": "", "role": "user"}],
  "total": 1,
  "offset": 0,
  "limit": 100
}

# Update user
PUT /api/v1/admin/users/user@example.com
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
