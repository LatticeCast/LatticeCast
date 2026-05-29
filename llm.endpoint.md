# LLM Context - API Endpoints

> Auth → `llm.user.md` | Storage → `llm.storage.md` | Schema → `llm.arch.airtable.md`

All routes under `/api/v1`. Rows keyed by `row_id` (int). Views keyed by `view_id` (int).

## Health & Debug

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/status` | None | Valkey & DB health |
| GET | `/settings` | None | Non-sensitive settings |
| GET | `/run-task/{seconds}` | None | Blocking task (debug) |
| GET | `/openapi-export` | None | Export OpenAPI spec |

## Auth (`/login`) · Sidebar (`/sidebar`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/login/config` | None | App config (auth_required) |
| POST | `/login/password` | None | Username+password (dev mode) |
| POST | `/login/{provider}/token` | None | OAuth code→tokens (google\|authentik) |
| GET | `/login/me` | Bearer | Current user info + config |
| PATCH | `/login/me/config` | Bearer | Shallow-merge user UI config |
| PUT | `/login/me/email` | Bearer | Update email |
| GET | `/sidebar` | Bearer | Workspace/table tree (PG function) |

## Workspaces (`/workspaces`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/workspaces` | User | Create (creator=owner) |
| GET | `/workspaces` | User | List user's workspaces |
| GET | `/workspaces/{wid}` | Member | Get workspace |
| PUT | `/workspaces/{wid}` | Owner | Rename |
| DELETE | `/workspaces/{wid}` | Owner | Delete |
| GET | `/workspaces/{wid}/members` | Member | List members |
| POST | `/workspaces/{wid}/members` | Owner | Add member |
| PUT | `/workspaces/{wid}/members/{uid}` | Owner | Update member role |
| DELETE | `/workspaces/{wid}/members/{uid}` | Owner | Remove member |

## Tables (`/tables`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables` | User | Create blank table |
| GET | `/tables` | User | List all tables (all workspaces) |
| GET | `/tables/{tid}` | Member | Full schema snapshot |
| PUT | `/tables/{tid}` | Member | Rename table |
| DELETE | `/tables/{tid}` | Member | Delete table |
| PATCH | `/tables/{tid}` | Member | Patch {view_order, default_view, col_order} |
| POST | `/tables/template/{kind}` | User | Create from template (pm\|crm\|blank) |

## Columns · Views · Dashboard

Per-aspect GETs removed — `GET /tables/{tid}` returns full schema. Column mutations return full schema. view_order/default_view via `PATCH /tables/{tid}`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables/{tid}/columns` | Member | Add column |
| PATCH | `/tables/{tid}/columns/{cid}` | Member | Update column |
| DELETE | `/tables/{tid}/columns/{cid}` | Member | Delete column |
| GET | `/tables/{tid}/views` | Member | List views (ordered) |
| GET | `/tables/{tid}/views/{vid}` | Member | Get single view |
| POST | `/tables/{tid}/views` | Member | Create view {name, type, config?} |
| PUT | `/tables/{tid}/views/{vid}` | Member | Update view |
| DELETE | `/tables/{tid}/views/{vid}` | Member | Delete view |
| POST | `/tables/{tid}/views/{vname}/blocks/{bid}/query` | Member | Dashboard LatticeQL query |

## Rows (`/tables/{tid}/rows`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tables/{tid}/rows` | Member | Create row (auto-doc for doc cols) |
| GET | `/tables/{tid}/rows` | Member | List (offset, limit, sort, filter_json) |
| GET | `/tables/{tid}/rows/{row_id}` | Member | Get single row |
| PUT | `/tables/{tid}/rows/{row_id}` | Member | Update row data |
| DELETE | `/tables/{tid}/rows/{row_id}` | Member | Delete row (+ MinIO cleanup) |
| GET | `/tables/{tid}/rows/{row_id}/doc` | Member | Get ticket doc (MinIO markdown) |
| PUT | `/tables/{tid}/rows/{row_id}/doc` | Member | Save ticket doc |
| GET | `/tables/{tid}/docs-exist` | Member | List row_ids with non-empty docs |
| GET | `/tables/{tid}/rows/{row_id}/col-doc/{cid}` | Member | Get per-column doc |
| PUT | `/tables/{tid}/rows/{row_id}/col-doc/{cid}` | Member | Save per-column doc |

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
