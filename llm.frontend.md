# LatticeCast — Frontend Architecture

The frontend is SvelteKit 2 with Svelte 5 runes. It treats the backend as the
source of truth and keeps a client cache in Svelte stores.

## Top-Level Rule

```text
UI event
  -> controller in lib/backend
  -> FastAPI and PostgreSQL/MinIO
  <- exact backend response
  -> controller updates the relevant store
  -> component $derived state recomputes
  -> GUI rerenders
```

This applies to reads and mutations. A component may own temporary UI state
(open modal, draft input, drag position), but it must not own a second copy of
server-backed tables, rows, views, workspaces, or members.

## Layer Map (`frontend/src/`)

| Layer | Paths | Responsibility |
|---|---|---|
| Route/load | `routes/` | Resolve URL, start reads, choose page composition |
| Controller | `lib/backend/`, `lib/api/` | Call API, validate response, update store |
| Model/cache | `lib/stores/*.store.ts` | Writable server cache and derived selectors |
| View | `routes/**/*.svelte`, `lib/components/` | Render stores through `$derived`; emit events |
| UI-only state | `lib/components/**/*.svelte.ts` | Svelte rune state tied to component behavior |

Plain store modules use `.store.ts`. Rune-bearing state uses `.svelte.ts`.

## Main Stores

| Store | Owns |
|---|---|
| `auth.store.ts` | Login token, provider, current user, application role |
| `table_schemas.store.ts` | Workspaces, tables, current IDs, schema cache, sidebar-derived data |
| `table_rows.store.ts` | Rows for the active table |
| `workspace_members.store.ts` | Member lists keyed by workspace UUID |
| `settings.store.ts` | Server-backed and local user preferences |
| `table_workflow.store.ts` | Workflow-specific derived helpers/state |

`table_schema.store.ts` and `table_views.store.ts` are compatibility re-exports
from the consolidated table cache. `tables.store.ts` is also a compatibility
and orchestration layer; do not create a new competing source of truth.

## Controllers

| File | Scope |
|---|---|
| `lib/backend/table_schemas.ts` | Bulk sidebar load -> `applySidebar()` |
| `lib/backend/tables.ts` | Tables, columns, schema patches, rows, ticket docs |
| `lib/backend/views.ts` | View reads and mutations -> `applySchema()` |
| `lib/backend/workspaces.ts` | Workspace/member CRUD -> workspace/member stores |
| `lib/backend/auth.ts` | Login/me/config calls |
| `lib/backend/storage.ts` | Generic user-file API |
| `lib/api/dashboard.ts` | Dashboard block queries |

Mutation endpoints for columns, views, and schema ordering return the full
schema snapshot. Controllers pass that response to `applySchema()`.

## Page Flow

- `routes/+layout.ts` is the central auth gate.
- `routes/+layout.svelte` owns the shared Sidebar + TopBar shell and hydrates
  the sidebar/user config.
- `routes/[workspace_id]/[table_id]/+page.ts` starts table/view/row reads.
- The table page derives columns, rows, filters, groups, and active view from
  stores plus `table-page.svelte.ts` UI state.
- Table, Kanban, Timeline, Dashboard, and Workflow are renderings of the same
  table/row data.

## Gotchas

- URLs may show `workspace_name`, but stores and API data use `workspace_id`.
- `table_id` can repeat across workspaces; pass `workspace_id` when resolving an
  uncached table.
- Use backend-provided option colors; do not invent a separate frontend palette.
- After a mutation, assert the response-driven store and visible derived GUI,
  not only the HTTP status.
- Read `.agent-skills/developing/svelte/SKILL.md` before structural Svelte work.
