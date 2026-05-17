# LLM Context - Frontend (v0.45)

> For general project context, see `llm.root.md`. For deployment, see `llm.deploy.md`.

## MVC Architecture

Frontend follows a strict MVC separation:

| Layer | Location | Extension | Purpose |
|-------|----------|-----------|---------|
| **Model** | `lib/stores/*.store.ts` | `.store.ts` only | Writable stores (`writable()`) — Read only FE SSOT data (cache of BE DB) |
| **View** | `routes/**/*.svelte`, `lib/components/**/*.svelte` | `.svelte` | UI rendering, `$derived` for display logic |
| **Controller** | `lib/backend/*.ts` | `.ts` | API calls, fetch/mutate, update stores |

**Rules:**
- `lib/stores/` contains ONLY plain `.store.ts` files — no `.svelte.ts`, no runes, no handlers
- `.svelte.ts` files (runes, `$state()`) go in `lib/components/` not in `stores/`
- All colors come from BE as hex — FE never stores color palettes

## Stores (Model layer — `lib/stores/`)

| Store | Exports |
|-------|---------|
| `auth.store.ts` | `authStore` — `{accessToken, provider, user}` |
| `menu.store.ts` | `workspaces`, `tables`, `currentWorkspaceId`, `currentTableId`, `currentWorkspace` (derived), `currentTable` (derived) |
| `table_schema.store.ts` | `columns`, `viewOrder`, `applySchema` |
| `table_views.store.ts` | `views` |
| `table_rows.store.ts` | `rows` |
| `tables.store.ts` | Re-exports from above + orchestrator functions (`loadTable`, `refreshRows`, etc.) + `IMPLICIT_TABLE_VIEW` constant + `error` writable |
| `settings.store.ts` | `darkMode` (server-backed via PATCH), `speechLang`, notifications (localStorage) |

## Controllers (API layer — `lib/backend/`)

Thin fetch wrappers. Each mutator updates the SSOT store directly after API success — no full refetch.

- `auth.ts` — `fetchMe`, login flows
- `tables.ts` — `fetchTable`, `fetchRows`, `createRow`, `updateRow`, `deleteRow`, `createColumn`, `updateColumn`, `deleteColumn`, `patchSchema`, `batchDocsExist`
- `views.ts` — `createView`, `updateView`, `deleteView`
- `workspaces.ts` — workspace + member CRUD, `fetchWorkspaces`
- `storage.ts` — MinIO file upload/download
- `http.ts` — shared `getAuthHeaders`, `getBearerHeader`

## Table Page (the god-page)

`routes/[workspace_id]/[table_id]/+page.svelte` — coordinates all table interactions.

Reactive state + handlers live in `lib/components/table/table-page.svelte.ts` (NOT in stores):
- `TablePageStore` class with `$state()` fields (~40 UI state vars)
- Handler methods: row CRUD, cell editing, column ops, view config, import/export, mouse events
- Exports singleton `s` — templates use `s.addingRow`, `s.handleAddRow()`, etc.
- Uses `_suppressPersist` counter to prevent view-switch race condition

## Components (`lib/components/table/`)

- `TableGrid.svelte` — spreadsheet grid (heaviest component)
- `KanbanBoard.svelte` / `TimelineView.svelte` / `dashboard/DashboardView.svelte`
- `TableToolbar.svelte`, `ViewSwitcher.svelte`, `GroupBySelector.svelte`
- `ContextMenu.svelte`, `RowExpandPanel.svelte`, `DocCellEditor.svelte`
- `AddColumnModal.svelte`, `ManageOptionsModal.svelte`, `CreateTicketModal.svelte`
- `ImportPreviewModal.svelte`, `ImportTemplateModal.svelte`
- `table.utils.ts` — pure helpers (parseCSV, applyFilters, sortRows, colorToStyle)
- `table-page.svelte.ts` — reactive UI state class (see above)

## Routing

| Route | Purpose |
|-------|---------|
| `/` | Home — redirect to last workspace or show empty state |
| `/login`, `/callback` | OAuth + password login |
| `/settings` | Per-user settings |
| `/[workspace_id]` | Workspace overview (table list, create table) |
| `/[workspace_id]/members` | Workspace member admin |
| `/[workspace_id]/[table_id]` | Table god-page (all views) |
| `/[workspace_id]/[table_id]/[row_number]` | Row detail / doc editor |

## Theme & Colors

`lib/UI/theme.svelte.ts` — light/dark theme tokens only (reactive `T` proxy).
No color palettes — all option colors (select/tags) are hex from BE.
`colorToStyle(hex)` in `table.utils.ts` renders as `background-color: ${hex}20; color: ${hex}`.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| SvelteKit | 2.x | Full-stack framework |
| Svelte | 5.x | Reactive UI (runes: `$state`, `$derived`, `$effect`) |
| Tailwind CSS | 4.x | Utility-first styling |
| TypeScript | 5.x | Type safety |
| Vite | 7.x | Build tool |
| ECharts | 5.6 | Dashboard charts |
| Playwright | 1.55.x | Browser testing |

## Build / Dev

- `npm run dev` — Vite dev server (in container)
- `npm run check` — svelte-check
- `npm run lint` — prettier + eslint
- `npm test` — vitest
- Adapter: `@sveltejs/adapter-static` (SPA)
