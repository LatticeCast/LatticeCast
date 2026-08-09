# LatticeCast — Generic Table Engine

This is Layer 1: all PM, CRM, workflow, and custom tables use the same workspace,
table, column, view, and row machinery. Templates seed configuration; they do
not create separate storage models.

## Data Model

```text
workspace (UUID identity)
  `-- table (workspace_id + table_id)
        |-- schema in tables.config
        |     `-- columns [{column_id, name, type, options}, ...]
        |-- views (per-table numeric view_id + config JSONB)
        `-- rows  (per-table numeric row_id + row_data JSONB)
```

Row values are keyed by column UUID, not by display name. Column position comes
from schema ordering. View display name and type live in the view config.

## Supported Concepts

- Column types include text, number, date/datetime, select, tags, checkbox,
  URL/contact types, and document cells.
- View types include table, kanban, timeline, dashboard, and workflow.
- View `0` is the frontend's implicit table/schema view and may have no
  `table_views` row.
- Select/tag option colors come from backend column options as hex values.
- PostgreSQL helpers manage expression/GIN indexes for searchable JSONB columns.

Consult migration functions and frontend types for the exact supported enum and
config fields; do not duplicate them in feature code.

## Mutation Contract

Column, view, ordering, and default-view changes are performed through PG
functions wrapped by `TableViewRepository`. The API returns one canonical schema
snapshot:

```text
{ columns, view_order, default_view, views }
```

Frontend controllers call the endpoint, pass that response to `applySchema()`,
and let derived state rerender the active view. Do not locally reconstruct the
expected schema after a mutation.

## Main Files

| Concern | Source |
|---|---|
| Table/row/view models | `backend/src/models/table.py`, `backend/src/models/row.py`, `backend/src/models/table_view.py` |
| Table and schema access | `backend/src/repository/table.py`, `backend/src/repository/table_view.py` |
| Table API | `backend/src/router/api/tables/`, `backend/src/router/api/rows.py` |
| Schema SQL | `migration/V*.sql` |
| Frontend controllers | `frontend/src/lib/backend/tables.ts`, `frontend/src/lib/backend/views.ts` |
| Frontend cache | `frontend/src/lib/stores/table_schemas.store.ts`, `frontend/src/lib/stores/table_rows.store.ts` |
| Main renderer | `frontend/src/routes/[workspace_id]/[table_id]/+page.svelte` |

## Resolution and Authorization

- Browser paths are `/<workspace>/<table_id>` with optional row/doc segments.
- The workspace path may be a UUID or display name; internal identity remains
  the UUID.
- Table names are case-insensitively resolved within accessible workspaces, so
  use workspace context to disambiguate duplicates.
- PostgreSQL RLS applies `read` to selects and `write` to mutations.
- `workspace_name` and `table_id` cannot contain `.` because both are path-facing.
