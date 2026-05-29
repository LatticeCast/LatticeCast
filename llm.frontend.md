# LLM Context - Frontend

> For general project context, see `llm.root.md`. For deployment, see `llm.deploy.md`.

## MVC Architecture

| Layer | Location | Purpose |
|-------|----------|---------|
| **Model** | `lib/stores/*.store.ts` | Writable stores — FE cache of BE SSOT |
| **View** | `routes/**/*.svelte`, `components/**/*.svelte` | UI rendering via `$derived` |
| **Controller** | `lib/backend/*.ts` | API calls → update stores |

Rules: stores = plain `.store.ts` only (no runes). `.svelte.ts` rune files go in `components/`. All colors hex from BE.

## Directory Tree (`frontend/src/`)

```
lib/
  api/dashboard.ts                  # dashboard block query client
  auth/{auth.service,login.svelte,pkce}.ts, providers/{google,authentik,index}.ts
  backend/{auth,config,http,storage,tables,table_schemas,views,workspaces}.ts
  charts/{EChart.svelte,ChartSanity.svelte,index,inject}.ts
  components/
    dashboard/{DashboardView.svelte, blocks/{Block,ChartBlock,ListBlock,NumberBlock}.svelte}
    layout/TopBar.svelte
    sidebar/{Sidebar,CreateWorkspaceModal}.svelte
    table/{TableGrid,TableHeader,TableGroupHeader,TableToolbar,ViewSwitcher,
           KanbanBoard,TimelineView,ContextMenu,RowExpandPanel,DocCellEditor,
           AddColumnModal,ManageOptionsModal,CreateTicketModal,ImportPreviewModal,
           ImportTemplateModal,GroupBySelector,GridAddRowFooter,GridDeleteCell,
           RowNumberCell}.svelte
    table/cells/{Checkbox,Date,Doc,Number,Select,Tags,Text,Url}Cell.svelte
    table/{table-page.svelte.ts, table.utils.ts, timeline.utils.ts,
           tableGrid.types.ts, dragReorder.svelte.ts}
    workflow/{WorkflowView,WorkflowNode,WorkflowGraphPanel,WorkflowFlowCapture}.svelte
    Portal.svelte
  icons/view.ts                     # SVG path constants per view type
  stores/{auth,settings,table_schema,table_schemas,table_views,table_rows,
          table_workflow,tables}.store.ts
  types/{auth,dashboard,json,table}.ts
  UI/{brand.ts, theme.svelte.ts, Button,Input,Label}.svelte
  utils/{date_time,url}.ts
routes/
  +layout.{svelte,ts}  login/  callback/{google,authentik}/  settings/  config/  debug/
  [workspace_id]/  [workspace_id]/members/  [workspace_id]/[table_id]/
  [workspace_id]/[table_id]/[row_id]/  [workspace_id]/[table_id]/[row_id]/doc/
```

## Stores (Model)

| Store | Key exports |
|-------|-------------|
| `auth.store.ts` | `authStore` — `{accessToken, provider, user, role}` |
| `table_schemas.store.ts` | **Sidebar SSOT** — `workspaces`, `tables`, `currentTableId`, `tablesByWorkspace`, `columns`, `viewOrder`, `defaultView`, `views`, `applySchema`, `applySidebar`, `initSidebar`, `resetSidebar` |
| `table_schema.store.ts` | Re-exports `columns, viewOrder, defaultView, views, applySchema` from `table_schemas` |
| `table_views.store.ts` | Re-exports `views` from `table_schemas` |
| `table_rows.store.ts` | `rows`, `resetRows` |
| `table_workflow.store.ts` | `screenToFlowStore`, `NODE_TYPES`, `NODE_COLORS`, `findColId`, `deriveGraphNames` |
| `tables.store.ts` | Backward-compat shim — re-exports stores + orchestrator fns (`loadTable`, `refreshRows`) |
| `settings.store.ts` | `darkMode` (server-backed), `speechLang`, notifications (localStorage), `hydrateFromServer` |

## Controllers (`lib/backend/`)

| File | Functions |
|------|-----------|
| `http.ts` | `getAuthHeaders`, `getBearerHeader` — shared auth header helpers |
| `auth.ts` | `fetchMe`, login flows |
| `tables.ts` | `fetchTable`, `fetchRows`, `createRow`, `updateRow`, `deleteRow`, `createColumn`, `updateColumn`, `deleteColumn`, `patchSchema`, `batchDocsExist` |
| `table_schemas.ts` | `fetchSidebar` — bulk `GET /api/v1/sidebar` → `applySidebar()` |
| `views.ts` | `createView`, `updateView`, `deleteView` |
| `workspaces.ts` | workspace + member CRUD, `fetchWorkspaces` |
| `storage.ts` | MinIO file upload/download |

## Key Pages

**Table god-page** (`routes/[workspace_id]/[table_id]/+page.svelte`): reactive state in `table-page.svelte.ts` — `TablePageStore` class, `$state()` fields (~40 UI vars), singleton `s`.
**Layout** (`+layout.svelte`): `Sidebar.svelte` + `TopBar.svelte`. `+layout.ts` = single auth gate. No per-page auth checks.

## Routing

| Route | Purpose |
|-------|---------|
| `/` | Home — redirect to last workspace |
| `/login`, `/callback/{google,authentik}` | OAuth + password login |
| `/settings`, `/config`, `/debug` | Per-user settings, app config, debug |
| `/[workspace_id]` | Workspace overview |
| `/[workspace_id]/members` | Member admin |
| `/[workspace_id]/[table_id]` | Table god-page (Table/Kanban/Timeline/Dashboard/Workflow) |
| `/[workspace_id]/[table_id]/[row_id]` | Row detail (`[row_id]/doc` = doc editor) |

## Charts

ECharts 5.6 via `lib/charts/`. `EChart.svelte` wrapper + `inject.ts` (`applyInjects` for `$inject: rows`). Dashboard blocks in `components/dashboard/blocks/`.

## Tech Stack

SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript 5, Vite 7, ECharts 5.6, @xyflow/svelte (workflow), Playwright 1.55. Adapter: `@sveltejs/adapter-static` (SPA). Dev: `npm run dev`, check: `npm run check`, lint: `npm run lint`, test: `npm test`.
