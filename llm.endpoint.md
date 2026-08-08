# LLM Context - API Endpoints

> Auth → `llm.user.md` | Storage → `llm.storage.md` | Schema → `llm.arch.airtable.md`

All routes under `/api/v1`. Rows keyed by `row_id` (int). Views keyed by `view_id` (int).

## Health & Debug

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/status` | None | DB health |
| GET | `/settings` | None | Non-sensitive settings |
| GET | `/run-task/{seconds}` | None | Blocking task (debug) |
| GET | `/openapi-export` | None | Export OpenAPI spec |

## Auth (`/login`) · Sidebar (`/sidebar`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/login/password` | None | Username+password → self-signed JWT |
| POST | `/login/{provider}/token` | None | OAuth code→tokens (google\|authentik) |
| GET | `/login/me` | Bearer | Current user info + config |
| PATCH | `/login/me/config` | Bearer | Shallow-merge user UI config |
| PUT | `/login/me/email` | Bearer | Update email |
| PUT | `/login/me/password` | Bearer | Set/change password |
| GET | `/sidebar` | Bearer | Workspace/table tree (PG function) |

## Workspaces (`/workspaces`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/workspaces` | User | Create (creator receives read+write+owner) |
| GET | `/workspaces` | User | List workspaces with a read grant |
| GET | `/workspaces/{wid}` | Read | Get workspace |
| PUT | `/workspaces/{wid}` | Owner | Rename |
| DELETE | `/workspaces/{wid}` | Owner | Delete |
| GET | `/workspaces/{wid}/members` | Owner | List members, aggregated to highest level |
| POST | `/workspaces/{wid}/members` | Owner | Add member with `level=read|write|owner` |
| PUT | `/workspaces/{wid}/members/{uid}` | Owner | Replace member access level |
| DELETE | `/workspaces/{wid}/members/{uid}` | Owner | Remove member |

## Tables (`/tables`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables` | Write | Create blank table |
| GET | `/tables` | User | List all tables (all workspaces) |
| GET | `/tables/{tid}` | Read | Full schema snapshot (`workspace_id` query param disambiguates names) |
| PUT | `/tables/{tid}` | Write | Rename table |
| DELETE | `/tables/{tid}` | Write | Delete table |
| PATCH | `/tables/{tid}` | Write | Patch {view_order, default_view, col_order} |
| POST | `/tables/template/{kind}` | Write | Create from template (pm\|crm\|workflow\|blank) |

## Columns · Views · Dashboard

Per-aspect GETs removed — `GET /tables/{tid}` returns full schema. Column mutations return full schema. view_order/default_view via `PATCH /tables/{tid}`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables/{tid}/columns` | Write | Add column |
| PATCH | `/tables/{tid}/columns/{cid}` | Write | Update column |
| DELETE | `/tables/{tid}/columns/{cid}` | Write | Delete column |
| GET | `/tables/{tid}/views` | Read | List views (ordered) |
| GET | `/tables/{tid}/views/{vid}` | Read | Get single view |
| POST | `/tables/{tid}/views` | Write | Create view {name, type, config?} |
| PUT | `/tables/{tid}/views/{vid}` | Write | Update view |
| DELETE | `/tables/{tid}/views/{vid}` | Write | Delete view |
| POST | `/tables/{tid}/views/{vname}/blocks/{bid}/query` | Read | Dashboard LatticeQL query |

## Rows (`/tables/{tid}/rows`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables/{tid}/rows` | Write | Create row (auto-doc for doc cols) |
| GET | `/tables/{tid}/rows` | Read | List (offset, limit, sort, filter_json) |
| GET | `/tables/{tid}/rows/{row_id}` | Read | Get single row |
| PUT | `/tables/{tid}/rows/{row_id}` | Write | Update row data |
| DELETE | `/tables/{tid}/rows/{row_id}` | Write | Delete row (+ MinIO cleanup) |
| GET | `/tables/{tid}/rows/{row_id}/doc` | Read | Get ticket doc (MinIO markdown) |
| PUT | `/tables/{tid}/rows/{row_id}/doc` | Read | Save ticket doc (route currently checks readability only) |
| GET | `/tables/{tid}/docs-exist` | Read | List row_ids with non-empty docs |
| GET | `/tables/{tid}/rows/{row_id}/col-doc/{cid}` | Read | Get per-column doc |
| PUT | `/tables/{tid}/rows/{row_id}/col-doc/{cid}` | Read | Save per-column doc (route currently checks readability only) |

## Storage (`/storage`) · Admin (`/admin/users`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/storage/files` | User | List files (prefix, max_keys) |
| GET | `/storage/file/{path}` | User | Download file |
| PUT | `/storage/file/{path}` | User | Upload file (multipart) |
| DELETE | `/storage/file/{path}` | User | Delete file |
| GET | `/storage/admin/files` | Admin | List all files (full paths) |
| POST | `/admin/users` | Admin | Create user (bootstrap account) |
| GET | `/admin/users` | Admin | List users (offset, limit) |
| GET | `/admin/users/{email}` | Admin | Get user by email |
| PUT | `/admin/users/{email}` | Admin | Update role |
| DELETE | `/admin/users/{email}` | Admin | Delete user (cascades) |
