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
- Docs are addressed blob cells: `/rows/{row}/blob/{column}/doc`. `/rows/{row}/doc` and `/col-doc/{column}` are compatibility routes.
- Normal routes require RLS-backed workspace access (`read`, `write`, `owner` as applicable).
