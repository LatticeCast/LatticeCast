# LatticeCast — Dashboard View

Dashboard is a table view type. Its blocks run aggregate LatticeQL queries over
the same rows used by Table, Kanban, Timeline, and Workflow views, then render
the returned rows as ECharts, numbers, or lists.

## Data and Query Flow

```text
table_views.config block
  -> POST /tables/{table_id}/views/{view_name}/blocks/{block_id}/query
  -> validate dashboard view and find block LQL
  -> compile LQL with workspace schema
  -> execute SQL through the RLS session
  -> { rows: [...] }
  -> frontend block renderer
```

The route uses `view_name`, not numeric `view_id`. The database view row still
uses the normal composite view identity.

## Config Concepts

- `layout` positions block IDs on a 12-column grid.
- `blocks` maps each block ID to a discriminated config with `kind`, `title`,
  and `lql`.
- Current block kinds are chart, number, and list.
- Chart blocks store an ECharts option object. `{"$inject":"rows"}` placeholders
  are replaced with query rows before rendering.
- Number blocks select one field from the first result row; list blocks render
  configured or inferred columns.

Exact Pydantic and TypeScript shapes live in the model files below.

## Backend Files

| File | Responsibility |
|---|---|
| `backend/src/models/view.py` | Dashboard and block config models |
| `backend/src/router/api/dashboard.py` | Access check, block lookup, query endpoint |
| `backend/src/config/lattice_ql.py` | Schema construction, compilation, cache invalidation |
| `backend/src/config/pg_cache.py` | PostgreSQL TTL cache helpers |
| `backend/src/repository/dashboard.py` | Execute compiled SQL |

The workspace schema used for compilation is cached in `private.cache` and must
be invalidated after column changes.

## Frontend Files

| File | Responsibility |
|---|---|
| `frontend/src/lib/api/dashboard.ts` | Fetch block rows |
| `frontend/src/lib/types/dashboard.ts` | Config and response types |
| `frontend/src/lib/components/dashboard/DashboardView.svelte` | Grid and config UI |
| `frontend/src/lib/components/dashboard/blocks/` | Block dispatcher/renderers |
| `frontend/src/lib/charts/EChart.svelte` | ECharts lifecycle and resize |
| `frontend/src/lib/charts/inject.ts` | Replace data injection markers |

## Extending Dashboards

Adding a block kind normally requires matching backend model, frontend type,
renderer, and dispatcher changes. It reuses the existing query endpoint unless
the query contract itself changes. Verify both query results and the visible
derived chart/list/number state.
