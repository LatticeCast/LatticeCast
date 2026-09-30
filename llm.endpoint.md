# API Map

All routes are `/api/v1`; decorators/OpenAPI are authoritative. Interactive docs: `/api/v1/docs`; machine spec: `/api/v1/openapi.json`.

| Area | Source/prefix |
|---|---|
| Auth/admin | `/login`, `/admin/users` |
| Workspaces/sidebar | `/workspaces`, `/sidebar` |
| Tables/schema/views | `/tables` |
| Rows/blob cells | `/tables/{table_id}/rows` |
| Dashboard blocks | `/tables/{table_id}/views/{view_name}/blocks` |
| Generic files | `/storage` |

- Table/schema mutations return a full schema snapshot; apply it to cache.
- A blob cell is addressed only as `/tables/{table}/rows/{row}/blob/{column}`. Its `kind` is a client-side picker/rendering hint; no `/doc` or `/col-doc` compatibility routes exist.
- Normal routes require RLS-backed workspace access (`read`, `write`, `owner` as applicable).
