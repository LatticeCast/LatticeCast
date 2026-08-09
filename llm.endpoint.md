# LatticeCast — API Map

All application routes are under `/api/v1`. The authoritative route signatures
are the FastAPI decorators in `backend/src/main.py` and
`backend/src/router/api/`; interactive docs are at `/api/v1/docs`.

## Route Groups

| Prefix | Main operations | Source |
|---|---|---|
| `/status`, `/settings` | Health and non-secret runtime settings | `backend/src/main.py` |
| `/login` | Password/OAuth login, current user, config, email, password | `router/api/auth.py` |
| `/admin/users` | Admin user CRUD | `router/api/admin/users.py` |
| `/workspaces` | Workspace CRUD and member access levels | `router/api/workspaces.py` |
| `/sidebar` | Bulk accessible workspace/table tree | `router/api/table_schemas.py` |
| `/tables` | Table CRUD, schema patch, templates, columns, views | `router/api/tables/` |
| `/tables/{table_id}/rows` | Row CRUD, ticket docs, column docs | `router/api/rows.py` |
| `/tables/{table_id}/views/{view_name}/blocks` | Dashboard block query | `router/api/dashboard.py` |
| `/storage` | Generic user-prefixed file CRUD and admin listing | `router/api/storage.py` |

## Table API Shape

- `GET /tables/{table_id}` returns identity plus the complete schema snapshot:
  columns, view order, default view, and ordered user views.
- Column and view mutations also return that full snapshot. Frontend
  controllers must apply it to the table cache.
- `PATCH /tables/{table_id}` accepts partial schema-order/default-view changes.
- `POST /tables/template/{kind}` creates a table through the shared template
  dispatcher; supported kinds come from the backend model/PG function.
- A `workspace_id` query parameter disambiguates equal table names in different
  workspaces.

## Row and Document API

- Row identity is `(workspace_id, table_id, row_id)`, while routes expose the
  table name and per-table numeric `row_id`.
- Row writes merge `row_data`, whose keys are column UUID strings.
- `/rows/{row_id}/doc` reads/writes the main Markdown document.
- `/rows/{row_id}/col-doc/{column_id}` handles a document-type column.
- `/docs-exist` batches document-existence lookup for the table UI.

## Access Model

- Public health/login exchange routes do not require an existing session.
- Normal data routes resolve a bearer token to a registered user and run with
  an RLS session.
- Workspace data reads require `read`; data mutation requires `write`;
  workspace/member administration requires `owner`.
- Admin application role is separate from workspace access level.

## Change Checklist

When an endpoint changes, update the backend response model, its frontend
controller/store application, focused E2E coverage, and this route map only if
the stable contract changed. Do not duplicate every request/response field here;
use OpenAPI and the Pydantic models for that detail.
