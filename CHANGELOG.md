# Changelog

## v0.50 — 2026-05-25 (UV images + docker log rotation + ws-id testids)

- Backend & e2e Dockerfiles rebased on the official
  `ghcr.io/astral-sh/uv` image; reproducible installs from `uv.lock`,
  no in-image `.venv`.
- Custom log rotation (`ServerTee.py`, cron, `daily.sh`) replaced by
  docker's `json-file` driver (100 MB × 50).
- Fix: `PUT /workspaces` 500 on rename (name-conflict query used
  `scalar_one_or_none`).
- Sidebar workspace `data-testid` keyed on `workspace_id` so renames
  don't break selectors.
- `developing-svelte` skill → v0.10.0 (BE-SSOT / FE-cache framing,
  e2e-first testing).

## v0.49 — 2026-05-21 (table page load + e2e fixes)

### Frontend — table page `+page.ts` load function

- **Table page data loading moved to `+page.ts`.** Replaced the async
  IIFE inside `$effect` with a SvelteKit `+page.ts` load function.
  Data (table schema, rows, views) is now fetched before the component
  mounts — eliminates the race condition where Playwright found stale
  DOM before the async effect completed. `loading` state and
  `tableLoaded` flag removed; `data-table-loaded="true"` is always set.

- **`untrack()` guard on view init effect.** The `$effect` that
  selects the initial active view now wraps its body in `untrack()`.
  Previously, reading `s.activeViewId` inside the effect made it a
  tracked dependency — any view switch via `handleViewChange` re-ran
  the effect, calling `s.reset()` and reverting `activeViewId` back to
  the Schema view. Only `data.table` and `data.urlViewId` (from props)
  are tracked now.

- **Workspace page uses SSOT store directly.** `+page.svelte` and
  `[workspace_id]/+page.svelte` now read `$workspacesStore` /
  `$tablesStore` instead of local `let workspaces` / `let tables`
  copies. Mutations (create, rename, delete) no longer manually splice
  the local array — the store is updated by the API call, and the
  derived UI re-renders automatically.

### Bug fixes — workspace rename navigation

- **Capture `isActive` before async `updateWorkspace`.** In
  `handleWsRename`, `activeWorkspace` is derived from the URL param
  matched against `workspace_name` in the store. After
  `updateWorkspace` mutated the store (changing the name), the derived
  value resolved to `null` and the `goto()` never fired. Fix: snapshot
  `isActive` before the async call.

### E2E test fixes

- **`test_create.py`** — URL pattern `**/{ws_name}/**` didn't match
  `/{ws_name}` (no trailing slash). Changed to `**/{ws_name}*`.

- **`test_rename.py`** — `wait_for_url` doesn't detect
  `history.replaceState` navigation. Replaced with Playwright's
  `expect(page).to_have_url(re.compile(...))` which polls the URL.

## v0.48 — 2026-05-21 (reduce $effect + default view fix)

### Frontend — reduce `$effect`, use `$derived` from SSOT stores

- **task-303 — setter-based persist in TablePageStore.** Eliminated
  the `$effect` that JSON-stringified 8 fields every tick to detect
  changes. View config now persists via explicit setter calls in
  `handleViewChange` / `applyViewConfig`. Removes effect #6.

- **task-304 — dark mode DOM toggle moved to `theme.svelte.ts`.**
  The `+layout.svelte` `$effect` that toggled `document.documentElement
  .classList` is replaced by a self-contained reactive block in the
  theme manager. Components import `T` — no layout effect needed.
  Removes effect #1.

- **task-305 — layout sidebar state uses SSOT store.** Eliminated
  the duplicate `$effect` in `+layout.svelte` that synced auth →
  sidebar visibility. Sidebar open/close now reads directly from
  `table_schemas.store.ts`. Removes effect #2.

- **task-307 — table view group-first then sort within each group.**
  `buildGroupedRows` in `table.utils.ts` now groups first, then
  applies sort config within each group — matching kanban behavior.
  Previously sorted globally then grouped, losing sort order at
  group boundaries.

### Bug fixes — `default_view` persistence

- **task-306 — FE: allow implicit Schema view as default.** When
  clicking Schema view (view_id=0, the implicit table view),
  `handleViewChange` now sends `default_view: null` to clear the
  stored default. On reload, null falls through to `candidates[0]`
  which is IMPLICIT_TABLE_VIEW.

- **task-309 — BE: `model_fields_set` for null clearing.** Changed
  `SchemaPatch` handler from `if data.default_view is not None:` to
  `if "default_view" in data.model_fields_set:`. Pydantic v2's
  field tracking distinguishes "not provided" from "explicitly null".

- **task-310 — V25 migration: `update_default_view` allows
  view_id=0.** PG function skips the `table_views` existence check
  when `p_view_id = 0` (the implicit Schema view sentinel is not
  stored in DB).

- **bug-312 — `fetchTable` writes `defaultView` to SSOT store.**
  `fetchTable` set `columns`, `views`, `viewOrder` but not
  `defaultView` — the store stayed stale after page load. Added
  `defaultView.set(table.default_view ?? null)`.

### Infrastructure

- **claude-bot v0.35.3 — dead worker window detection.** Orchestrator
  `wait_finish()` checks every 30s if tmux worker windows still exist.
  If all workers died (watchdog kill, crash), resets stuck
  `in_progress`/`testing` tickets to `todo` immediately instead of
  burning the full 900s timeout.

- **developing-svelte v0.8.0** — added e2e testing guidance, snapshot
  verification rules.

- **e2e directory renamed** from `test-e2e/` to `e2e/`.

- **Backend Dockerfile** — `UV_LINK_MODE=copy` for IPv6 compatibility.

## v0.47 — 2026-05-20 (sidebar preload + data recovery)

### Performance — first-table-click latency removed

- **New PG function `public.get_user_sidebar(uid)`** (V24) returns
  `{workspaces, tables}` in one call. SECURITY DEFINER, GRANT EXECUTE
  to `app` + `mgr`. Two separate arrays (not joined) so empty
  workspaces still appear.

- **New BE endpoint `GET /api/v1/sidebar`** — thin passthrough, 13
  lines. Heavy work stays in PG.

- **New FE store `table_schemas.store.ts`** (replaces `menu.store.ts`)
  + `fetchSidebar()` controller. Layout and home pages call it once on
  mount; every table's schema (columns, view_order, default_view) is
  already in memory before the user clicks. Eliminates the schema
  round-trip on first table click — only `rows` still fetches per
  open.

- Sidebar now does **1 call** instead of `Promise.all([
  fetchWorkspaces(), fetchTables() ])`.

### Data recovery — local DB rebuild

- Renamed live `db` → `db_0518` (backup) and applied V1–V24 to a fresh
  `db`. Per-table cross-database recovery via `dblink`: `auth.users`,
  `gdpr.user_info`, `public.{workspaces, workspace_members, tables,
  rows, table_views}`.

- **V23 merge fixup during recovery** — old `public.table_schemas` was
  joined into `public.tables.config` (column, view_order,
  default_view) along with `created_by` / `updated_by`.

- **view_order rebuilt** — 22 views had no entry in
  `tables.config.view_order` (stale config carried over from
  pre-merge). Rebuilt from actual `table_views` rows, set
  `default_view` to the smallest view_id where missing.

### E2E — `lattice` admin unblock

- Discovered `lattice` user had `role='user'` not `'admin'` in both
  old and new DB, so 5 e2e tests hit `403 Admin access required`
  via the `admin_token = login("lattice")` fixture. Promoted via
  `UPDATE auth.users SET role='admin'` on this DB. (Seed migration
  was prepared then withdrawn; data-only fix until the seed strategy
  is settled.)

- Net suite: **46 pass / 1 fail**. Remaining deterministic failure
  is `tables/test_column_add.py::test_column_add` — the
  `kanban-card-fields-btn` doesn't show after creating a kanban
  view (real UI bug, not flake).

## v0.46 — 2026-05-17 (pytest migration + E2E fixes + Hide Fields removed)

### E2E Tests — pytest migration

- **All 47 e2e tests migrated to pytest.** Converted from standalone
  scripts (`python3 test_*.py`) to pytest with shared fixtures
  (`conftest.py`: `authed_page`, `admin_token`, `workspace`, `pm_table`,
  `snapshot`). Tests organized into domain folders: `tables/`,
  `table_views/`, `workspace/`, `columns/`, `rows/`.

- **`conftest.py` shared fixtures.** `authed_page` handles login +
  browser connection; `workspace` creates/tears-down a workspace per
  test; `pm_table` creates a PM-template table with views.

### E2E Tests — fixes

- **`test_kanban_drag_card`:** replaced Playwright `drag_to()` with
  manual `DragEvent` dispatch — native HTML5 drag detached the card DOM
  node during Playwright's mouse simulation.

- **`test_workspace_rename`:** fixed trailing-slash URL assertion.

- **`test_workspace_create`:** removed duplicate-name error check
  (workspace names are intentionally non-unique); fixed teardown to
  verify delete by `workspace_id`.

- **`test_col_hide`:** deleted (feature removed).

- **`test_column_add`:** added `networkidle` wait + longer timeout for
  persistence step.

### Frontend

- **Hide Fields feature removed.** Removed `hiddenCols` from
  `table-page.svelte.ts`, `TableToolbar.svelte`, `TableHeader.svelte`,
  `TableGrid.svelte`, `ContextMenu.svelte`, `table.utils.ts`, and
  `+page.svelte`. Feature was unused and untested.

- **DocCellEditor always opens textarea.** Fixed race where `docEditing`
  stayed false when content loaded before click — textarea now mounts
  unconditionally after load.

- **Select cell `data-testid` persists across edit mode.** Wrapped
  edit-mode `<select>` in `<span data-testid="select-cell-...">` so
  Playwright can find the element after double-click triggers edit mode.

---

## v0.45 — 2026-05-17 (Merge table_schemas + FE store split + color unification)

### Database

- **V23: `public.table_schemas` merged into `public.tables`.**
  The two tables were always 1:1. `config`, `created_by`, `updated_by`
  columns absorbed into `public.tables`. All 10 PG functions rewritten
  (`add_column`, `update_column`, `delete_column`, `update_col_order`,
  `update_view_order`, `update_default_view`, `create_view`, `update_view`,
  `delete_view`, `create_table_from_template`). Auto-create trigger and
  RLS policy on old table dropped.

### Frontend

- **Option colors unified to hex-only.** Removed `TAG_COLORS` (Tailwind
  class objects) and `CHOICE_HEX_PALETTE` from theme. `colorToStyle()`
  now takes hex from BE — single render path for select/tags/status.

- **`tablePage.store.svelte.ts` split.** Stores directory now only
  contains plain `.store.ts` files. Reactive class (`$state()` + handlers)
  moved to `components/table/table-page.svelte.ts`. `tables.store.ts`
  restored with re-exports + orchestrators + `IMPLICIT_TABLE_VIEW`.

- **`tables.store.ts` shim consumers rewired** (S3+S4 of Epic #271).
  All 8 consumers import directly from canonical SSOT stores and
  controllers. View-switch race condition fixed with `_suppressPersist`
  counter.

### Backend

- **`table_view.py` query updated.** `SELECT config FROM public.tables`
  replaces `public.table_schemas` reference.

---

## v0.44 — 2026-05-17 (Dashboard view + row handler cleanup)

### Frontend

- **Row handlers cleaned up — no more `refreshRows()` after mutations.**
  All row CRUD (add, delete, duplicate, edit, toggle, tags) now just calls
  the controller function which updates the SSOT `rows` store directly.
  Removes redundant full-table refetches after every cell edit.

- **Optimistic temp-row pattern removed from `handleAddRow`.** Both "+"
  button and cell-click now follow the same path: call `createRow` →
  controller appends to store → `$derived` re-renders. No more
  double-append bugs or visual glitches.

- **Dashboard view type added to "Add View" panel.** New dashboards
  initialize with `{ layout: [], blocks: {} }` and provide an "Edit JSON"
  button for configuring blocks/layout inline.

- **View icons extracted to `lib/icons/view.ts`.** SVG paths stored as a
  `Record<string, string>` map — ViewSwitcher uses a single dynamic
  `<path d={...}>` instead of duplicated inline SVGs.

### Backend

- **`TableViewRepository.get_by_name()` added.** Dashboard block query
  endpoint was calling a non-existent method → 500 on every block load.
  Fix: query `config->>'name'` to resolve view by display name.

### Examples

- **`crm_demo.py` made idempotent.** Checks if table exists before
  delete+recreate. Shows user + workspace in output. Accepts `--workspace`
  flag to target a specific workspace by name or ID.

---

## v0.43 — 2026-05-17 (FE MVC refactor + BE table-create fix)

### Frontend — MVC SSOT architecture

- **Three-layer split: Model / Controller / View.**
  All FE state now flows: user action → Controller (`lib/backend/*.ts`)
  calls BE API → BE returns updated JSON → Controller writes to Model
  (stores) → View (`$derived` from stores) auto-re-renders. Like HTMX
  but at data granularity — stores hold the exact JSON shape PG returns.

- **New SSOT Model stores** (`lib/stores/`):
  - `table_schema.ts` — columns, viewOrder, defaultView + `applySchema()`
  - `table_views.ts` — views array (from BE response, not derived)
  - `table_rows.ts` — rows array
  - `menu.ts` — workspaces, tables, currentWorkspaceId, menuOpen +
    derived `currentWorkspace`, `workspaceTables`, `currentTable`

- **Controller layer** (`lib/backend/*.ts`):
  - `tables.ts` — every column/row/table mutation now calls BE AND
    writes the response to the SSOT store. One function call = API +
    store update.
  - `views.ts` — view CRUD calls BE then `applySchema()`.
  - `workspaces.ts` — workspace CRUD calls BE then updates menu store.

- **`+page.svelte` refactored from 1149 → 413 LOC.** All duplicate
  local `$state` and handler functions removed. Page now uses the
  `TablePageStore` class (`s`) for UI state + handlers. Data rendering
  is purely `$derived` from SSOT stores.

- **`types/table.ts` reorganized.** Types explicitly annotated as the
  shared PG → BE (passthrough) → FE contract. `TableSchema` is the
  single shape all three layers agree on.

- **`tables.store.ts` retained as backward-compat re-export shim.**
  Existing consumers continue to work unchanged; new code imports
  directly from the SSOT stores + controllers.

### Migration

- **V22 — fix `delete_column` "column not found" on every call.**
  The `WHERE c ->> 'column_id' <> p_column_id` filter removed the
  target column before `bool_or` could check for it → `v_found`
  always NULL → exception. Fix: separate existence check with
  `IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements WHERE ...)`,
  then filter. Verified via `e2e_test_column_delete`.

### Backend

- **Fix table creation 500 (template + blank).** `create_from_template`
  did `commit()` between the PG function call and the SELECT-back query.
  After commit, a new implicit transaction started where RLS's
  `app.current_user_id` (session-level `set_config`) worked but the
  `STABLE`-cached `check_workspace_member` from the previous statement
  wasn't re-evaluated. Fix: SELECT before commit — both run in the
  same transaction where the inserted row is unconditionally visible.

### E2E

- **`e2e_test_column_delete.py`** — verifies delete propagates across
  Table, Kanban (group-by + card-fields), and Timeline views, plus
  durability after navigation.

- **`e2e_test_workspace_member_remove.py`** — fixed flaky redirect
  detection (`wait_until="commit"` + `wait_for_url` instead of
  `networkidle`).

## v0.42 — 2026-05-15 (date-index fix + modular e2e + docs catch-up)

### Migration

- **V18 — fix `create_row_data_index()` for date/datetime columns.**
  V11's index helper lumped `date`/`datetime` with `number` and cast
  `row_data ->> col` to `::NUMERIC`, which raises on every insert into a
  table containing a date column (ISO-8601 strings can't cast to numeric).
  V18 adds `immutable_iso_to_ts(TEXT) → TIMESTAMP` (an `IMMUTABLE STRICT`
  wrapper — required for use inside index expressions), splits the
  `number` branch from a new `date`/`datetime` branch that uses the new
  helper, and walks `table_schemas` to drop+rebuild every existing broken
  date/datetime partial index. Idempotent — re-running is safe.
- **`test_migration_schema.py`** verifies `immutable_iso_to_ts` exists and
  that `immutable_iso_to_ts('2025-05-15')::DATE::TEXT` round-trips
  correctly.

### Backend

- **`TableViewRepository.get_schema()` retired.** Every call site
  (`rows.py` doc-template injection, doc-column filtering on
  create/update/delete; `lattice_ql._build_schema`) now uses
  `get_tables_schema()` and reads `["columns"]`. One read shape — the
  full schema dict — instead of two near-duplicate methods. Removes
  the last lingering v0.39-era surface from the BE.

### E2E infrastructure

- **Monolithic `browser/e2e_test.py` broken up.** Per-task test scripts
  share a small toolkit instead of duplicating bootstrap and assertions:
  - `bootstrap.py` — PG INSERT admin user (idempotent) + BE
    `/login/password` → `/admin/users` → workspace resolve. Returns
    `{admin, user}` dicts with tokens + IDs for tests to consume.
  - `e2e_helper.py` — shared `E2E` context: Playwright page + psycopg2
    cursor, plus `assert_db()` / `assert_visible()` helpers so each step
    can verify DB state and UI state in one place.
  - `snapshot_decorator.py` — opt-in `@snapshot` per-step screenshot.
    No-op unless `--snapshot` flag is passed; captures even on failure
    (try/finally) so a broken run still shows the progression up to the
    failing step. Output goes to `/output/<step>.png` (bind-mounted to
    `.browser/` on host).
  - `test_e2e_auth.py` — admin login / logout / user login, each step
    verifying both `auth.users.role` in DB and the corresponding UI
    state.
  - `test_e2e_workspace_table_create.py` — workspace create, blank
    table create, PM template table create, sidebar listing — same
    DB+UI dual-verify pattern.
- **Browser container can reach DB and BE.**
  `browser/Dockerfile` now installs `psycopg2-binary` + `requests`
  alongside Playwright. `docker-compose.yml` exposes `db` on host port
  `15432` and injects `DATABASE_URL` + `BASE_URL` into the browser
  service so scripts work the same whether run inside the container or
  on the host.

### Docs

- **`llm.arch.auth.md`, `llm.arch.db.md`, `llm.root.md`, `llm.user.md`
  caught up with v0.40 reality.** They still described the pre-squash
  world (`auth.gdpr` + `public.user_info` split, `login_mgr` role,
  `search_path=auth` only, `widgets` instead of `blocks`,
  chart.js+svelte-chartjs instead of ECharts). All four now reflect:
  the merged `gdpr.user_info` schema (email + user_name + config in
  one row), the `mgr` role with `BYPASSRLS`, the V15 explicit
  grants (default-priv machinery silently skips dba_user-owned tables),
  RLS shape per table, `search_path=public,auth,gdpr` on both engines,
  and the new `/me/config` + `/me/email` endpoints.

## v0.41 — 2026-05-14 (post-squash bugfixes + e2e test)

### Bugfixes caught via the new e2e suite

- **POST /workspaces 500.** New V17 `create_workspace` SECURITY DEFINER
  PG function inserts workspace + owner-member atomically. Previously
  RLS-blocked itself: creator wasn't a member yet at INSERT time. BE
  route delegates to the function.
- **PATCH /tables/{tid}/columns/{cid} 500 on color/options edit.**
  BE repo CASTed `column_id AS uuid`, but V13's `update_column` /
  `delete_column` take `p_column_id TEXT` (they string-match into
  the JSONB columns array). Dropped the cast.
- **View-config writes (group_by / sort_by / card_fields) "looked
  dead" in the FE.** BE view-CRUD returned only raw PG output
  (`{columns, view_order, default_view}`) without merging `views[]`.
  FE's `applySchema()` then nuked the views store. All write methods
  on `TableViewRepository` now `return await self.get_tables_schema()`
  so every response carries the full schema including views[].
- **`/login/me` + `/me/config` returned 403 / missing fields.** Three
  routes used `get_session` (no RLS context); `gdpr.user_info`'s
  RLS policy filters by `app.current_user_id`, which was unset →
  zero rows → 403. Switched to `get_rls_session`.

### Testing

- **New `browser/e2e_test.py`.** Tracked Playwright script that
  exercises the user-visible flows: workspace / blank table / PM
  template / column color / view config / me-config. Each step
  independent, prints pass/fail, exits non-zero on failure.
  Mounted live at `/scripts/` via the new `./browser:/scripts`
  compose volume — no image rebuild needed to iterate.
  ```bash
  docker compose --profile browser up -d browser
  docker compose exec browser python3 /scripts/e2e_test.py
  ```

### Known follow-up before AWS launch

- `get_first_owned_workspace` can transiently return a workspace
  whose RLS check doesn't match the caller after a workspace burst.
  Pass `workspace_id` explicitly in clients for now; need to audit
  the ORDER BY + ownership-role join.
- `_build_response` in admin/users.py reads via app_session so the
  201 response after create-user shows `email: ""` / `user_name: null`.
  Cosmetic — the user is created correctly. Switch to login_session
  for the response build.

## v0.40 — 2026-05-14 (pre-AWS migration squash + schema rewrite)

> **Major-version jump v0.3x → v0.4x.** Not incremental. The whole
> migration history is replaced, BE models are rewritten, FE pivots
> to a single-shape full-schema read pattern, and identifiers change
> (`row_number` → `row_id`, `view_name` → `view_id`). This is the
> last allowed checksum reset — V1-V14 are the locked baseline for
> AWS SaaS launch. From here on, V15+ is forward-only forever.

### Migrations squashed, then locked

- **Final checksum reset.** All prior migrations (V1-V42) are squashed
  into a clean V1-V14 set covering init, users, workspaces, tables,
  rows, table_views, RLS policies, and the index/template/schema/view
  helper PG functions. Pre-launch baseline — from here on it's
  forward-only forever. (Saved in memory: any "let's just squash
  again" idea post-launch must be refused.)
- **V15 — explicit role grants + BYPASSRLS.** V1's
  `ALTER DEFAULT PRIVILEGES FOR ROLE dba` silently no-ops because
  tables are owned by `dba_user` (login user), not the `dba` group
  role. V15 re-grants table-level CRUD to `app` and `mgr` on
  public/auth/gdpr, and sets `BYPASSRLS` on `mgr_user` (PG role
  attributes don't inherit through GRANT). Without this, the login
  session couldn't see any rows before a user was authenticated and
  the app session couldn't see its own tables.
- **V16 — `table_views.view_id` DEFAULT 0.** V9 set the default to 1,
  which silently bypassed the BEFORE INSERT trigger (which only fires
  on NULL or 0). Result: the second INSERT into the same table
  collided on PK. Dropped the default so the trigger always assigns
  `MAX(view_id)+1`.
- **V17 — `create_workspace` SECURITY DEFINER.** POST /workspaces
  used to RLS-block itself: creator wasn't a member yet at INSERT
  time. New PG function inserts workspace + owner-member atomically,
  bypassing RLS for the bootstrap.

### Architecture

- **BE is thin; PG functions own business logic.** Schema mutations
  (`add_column` / `update_column` / `delete_column` / `create_view` /
  `update_view` / `delete_view` / `update_view_order` /
  `update_default_view` / `update_col_order` /
  `create_table_from_template`) live in V11-V14 and run atomically
  in one transaction each. BE repositories are one-line wrappers —
  `await session.execute(SELECT <fn>(...))` and return the JSONB.
  No Python-side coordination, no duplication. Multi-worker safe.
- **Full schema in one shape.** Every read (`GET /tables/{tid}`) and
  every mutation (column / view / order / default-view) returns the
  same `{columns, view_order, default_view, views}` JSONB. The FE
  replaces its local store from that one response and never derives
  schema state locally. Per-aspect GETs (`/view-order`, `/col-order`)
  removed.
- **`view_id` (BIGINT) replaces `view_name` (string) as the view
  identifier.** Mirrors how columns use `column_id`. Display name +
  view type live inside the `config` JSONB; PG functions match by
  `view_id`. Route is `PUT/DELETE /tables/{tid}/views/{view_id}`.
  FE stores numeric ids; `IMPLICIT_TABLE_VIEW` has sentinel
  `view_id: 0`.
- **`row_number` → `row_id`.** Rename across backend models, repository,
  API routes, frontend types, components, and SvelteKit route params
  (`[row_number]` directory → `[row_id]`).
- **`column.position` removed.** Array index IS the column position
  now. Column order lives in `table_schemas.config.col_order`.

### Identity

- **PII merged into `gdpr.user_info`.** The old `public.user_info` +
  `auth.gdpr` split collapses into one row per user with
  `(user_id, email, user_name, config)`. A GDPR purge drops one row
  (or the whole schema) without touching `auth.users` or workspace
  audit trails. BE `UserInfo` SQLModel, repository, and routers all
  updated; `Gdpr` model deleted.
- **Engine search_path** now includes `gdpr` for both app + login
  engines; `mgr_user` (was `login_user`) backs the login session.
  POSTGRES_LOGIN_PASSWORD env var renamed to POSTGRES_MGR_PASSWORD.

### v41 bugfixes (caught via the new e2e suite)

- **POST /workspaces 500.** Fixed via V17 above.
- **PATCH /tables/{tid}/columns/{cid} 500 on color/options edit.**
  BE repo CASTed `column_id AS uuid`, but V13's `update_column` /
  `delete_column` take `p_column_id TEXT` (they string-match into the
  JSONB columns array). Dropped the cast.
- **View-config writes (group_by / sort_by / card_fields) "looked
  dead" in the FE.** BE view-CRUD returned only raw PG output
  (`{columns, view_order, default_view}`) without merging `views[]`.
  FE's `applySchema()` then nuked the views store. All write methods
  on `TableViewRepository` now `return await self.get_tables_schema()`
  so every response carries the full schema including views[].
- **`/login/me` + `/me/config` returned 403 / missing fields.** Three
  routes used `get_session` (no RLS context); `gdpr.user_info`'s
  RLS policy filters by `app.current_user_id`, which was unset →
  zero rows → 403. Switched to `get_rls_session`.

### Testing

- **New `browser/e2e_test.py`.** Tracked Playwright script that
  exercises the user-visible flows: workspace / blank table / PM
  template / column color / view config / me-config. Each step is
  independent, prints pass/fail, exits non-zero on any failure.
  Mounted live at `/scripts/` via the new `./browser:/scripts`
  compose volume — no image rebuild needed to iterate.
  ```bash
  docker compose --profile browser up -d browser
  docker compose exec browser python3 /scripts/e2e_test.py
  ```

### Known follow-up before AWS launch

- `get_first_owned_workspace` can transiently return a workspace
  whose RLS check doesn't match the caller after a workspace burst.
  Pass `workspace_id` explicitly in clients for now; need to audit
  the ORDER BY + ownership-role join.
- `_build_response` in admin/users.py reads via app_session so the
  201 response after create-user shows `email: ""` / `user_name: null`.
  Cosmetic — the user is created correctly. Switch to login_session
  for the response build.

## v0.32 — 2026-05-14

### Color UX overhaul
- **Picker swapped to `vanilla-colorful` web component.** `<hex-color-picker>`
  replaces the 3-slider HSL stack from task-263. ~4KB, no Svelte runtime
  overhead. Standard 2D saturation/value pad + horizontal hue bar + hex
  input. No text-selection-on-drag bug because the lib uses pointer events
  with its own capture. Lazy client-side import (the lib calls
  `customElements.define()` at module load, browser-only). Apply-on-close
  so live drag updates do not race the modal's reactive state.
- **Outlined choice pills.** `colorToStyle()` for hex/hsl colors now emits
  `background-color: <color>20` (12% alpha tint) + colored border + colored
  text instead of a solid fill. Reads as "tagged with this color" without
  flooding the cell. Legacy `bg-*` Tailwind classes keep their pastel-fill
  look (same visual weight).
- **PM/CRM template colors are hex (V42).** `_build_template_columns`
  recreated via `CREATE OR REPLACE` with semantic hex values: Type
  (epic/story/task/bug), Status (todo/in_progress/testing/debugging/review/
  done/merged), Priority (critical/high/medium/low), CRM Stage
  (lead/qualified/proposal/won/lost). Existing tables keep their Tailwind
  class colors and render unchanged; new tables get the hex palette which
  the new picker can edit directly.
- **`addChoice()` random colors.** New select/tags options get a random
  vivid hex: hue 0-359, saturation 60-75%, lightness 55-65%. Replaces the
  cyclic 10-color preset list.

## v0.31 — 2026-05-13

### Bug fixes
- **`TableRepository.create()` 500 (root-cause patch).** The
  `trg_tables_create_schema_and_order` AFTER INSERT trigger writes extra
  rows in the same transaction, leaving the ORM instance unrefreshable.
  task-256's audit had incorrectly marked `table.py:29` attached-safe.
  Switched to raw `INSERT` + `SELECT` (same pattern as bug-252/253).
- **`_index_name()` rejects non-ASCII table_id.** Names like `出國`
  blew up `create_row_data_index`'s `^idx_rd_[A-Za-z0-9_]+$` regex.
  Falls back to a SHA1[:12] hash when any non-ASCII char is present.
- **PM template silently lost views.** A failing `create_column_index`
  call poisoned the transaction, swallowed the exception, and the
  subsequent view inserts no-op'd — leaving only the implicit Table.
  Now rolls back on the failure and sets `Sprint Board` as the default
  view.
- **`Failed to fetch` / `Workspace not found` after table-router split.**
  The post-v0.30 `tables.py` split left `crud.py` with empty path on
  an empty-prefix router; FastAPI's auto-301-on-trailing-slash sent
  `/api/v1/tables` → `/api/v1/tables/`, and the browser dropped the
  Authorization header on redirect. Refactored: `crud.py` now declares
  `prefix="/tables"` itself, `__init__.py` is pure composition.
- **Docker backend build failed on transient pypi blip.** `uv`'s
  default 30s timeout was too tight. `ENV UV_HTTP_TIMEOUT=180` in
  the backend Dockerfile.
- **bug-266 — picked color not applied in all render sites.** task-263
  changed `getChoiceColor()` to return `{cls, style}` but only updated
  TagsCell + SelectCell. TableGrid, TableGroupHeader, TimelineView,
  KanbanBoard lane headers, and the row-expand panel all still read
  the old `{bg, text, border}` shape → custom colors looked blank.
  Migrated every site to the new `class={cs.cls} style={cs.style}`
  pattern.
- **bug-269 — DnD reorder did not persist.** Two bugs: `reorderViews`
  in the store never updated the local `views` writable after the API
  call (visual reverted on reload), and the column-reorder insert
  formula `toIdx > fromIdx ? toIdx - 1 : toIdx` was a no-op when
  dragging one step right (adjacent case).

### Polish
- **task-267 — sort labels are type-aware.** Number columns show
  `Ascending (1 → 9)`, date shows `Oldest first`, select/tags shows
  `Defined order`, checkbox shows `Unchecked first`. Text/url/doc
  keep the original `A → Z`. New `sortLabels(type)` helper in
  `table.utils.ts`; the three duplicate context-menu sites all use it.
- **task-268 — implicit first view is "Schema", pinned.** The
  always-present first tab now reads `Schema` instead of `Table`,
  cannot be renamed, deleted, or dragged. Server-side guard in
  `views.py` rejects user-created views named `Schema`
  (case-insensitive) with 400.

### Known follow-ups
- **bug-265 — color picker rewrite is parked.** The 3-slider HSL stack
  shipped in task-263 is bad UX; the spec is a hue-bar + 2D S/L-square
  picker. First attempt TIMEOUTed on the bot; partial work is in
  `git stash`. Needs to be split (build standalone `ColorPicker.svelte`,
  then wire into `ManageOptionsModal`) before retry. *(Resolved in v0.32
  via `vanilla-colorful` web component.)*

## v0.30 — 2026-05-10

### User-facing features
- **task-242 — edit own email.** New `PUT /api/v1/login/me/email`
  through `login_mgr` role to write `auth.gdpr.email`. 409 on
  duplicate (`UNIQUE` constraint from V10). New `/settings` page.
- **task-243 — create workspaces from sidebar.** Wired the existing
  `POST /workspaces` to a `+ New Workspace` modal in the sidebar.
- **task-244 — workspace members page.** `/<workspace>/members`
  lists members as `<user_name> (<email>)`, owner can add by email
  (server resolves to `user_id` UUID), change role, remove. New
  `PUT /workspaces/{id}/members/{user_id}` for role change.
  Last-owner guard on demote/remove. Members list joins
  `auth.users` + `auth.gdpr`.
- **task-245 — members page header shows workspace name.**
  `"<workspace_name> Members"`, with deep-link sync.
- **task-247 + bug-246 — dark mode coverage.** `/`, `/settings`, and
  `/config` all honor the dark toggle. New theme tokens
  `settingsHeroBg`, `selectedBorder`, `selectedBg`, `toggleTrackBg`
  in `theme.svelte.ts`. No more raw `bg-white` / `bg-gray-*` /
  `from-blue-*` in those routes.
- **task-248 + task-250 — workspace home is path-based.**
  `/<workspace_name>/` shows just that workspace's tables (tab
  strip switches between workspaces). The `/?workspace=<uuid>` query
  shape from task-248's first pass is gone. `/` redirects to the
  first or last-visited workspace. `+ New Workspace` button at the
  end of the tab strip.
- **task-249 — pretty URLs.** UUID in the address bar gets rewritten
  to `workspace_name` via `history.replaceState`. Pasted UUID URLs
  load correctly and then prettify. Backend still receives UUID —
  no API surface change.
- **task-251 — Members icon on workspace home header.**
- **task-261 — drag-and-drop column reorder + view tab reorder.**
  Native HTML5 DnD replaces the ←/→ click buttons.
- **task-264 — Table view group-by persists.** The Table view's
  group-by selection now round-trips through the view config the
  same way Kanban's does. Fixed a `$viewsStore` reactive loop that
  was re-firing the persist effect.

### Bug fixes
- **bug-252 / bug-253 — `Failed to create view` / `Failed to create
  PM template` 500s.** Root cause: `TableViewRepository.update()` and
  `.create()` called `session.refresh()` on instances detached after
  raw-SQL `INSERT`s. Migrated both to raw UPDATE/INSERT + SELECT
  (same pattern as `RowRepository.create()`).
- **bug-254 — `+ New Workspace` showed error after success.** Sidebar
  store wasn't updated until after navigation, and the `goto()` used
  UUID instead of name. Workspace now added to the local writable
  immediately + navigated to `/<workspace_name>/`.
- **bug-255 — members page didn't reload when switching workspaces
  via sidebar.** SvelteKit reuses the page component across same-shape
  routes; `onMount` doesn't re-fire. Swapped to an `$effect` tracking
  `params.workspace_id`.
- **task-256 — `session.refresh()` audit.** All 11 remaining call
  sites verified attached-safe and annotated with a comment.
  Regression tests added for the high-risk paths.

### Refactor
- **task-258 — split `router/api/tables.py` (756 LOC) → 5 sibling
  files** under `router/api/tables/` (`crud`, `columns`, `views`,
  `templates`, `_shared`). Each ≤ 250 LOC; URLs unchanged.
- **task-260 — zero `no-unused-vars` lint errors** across FE in a
  single commit.
- **examples/crm_demo.py** — stdlib-only Python script that creates
  a demo CRM table, seeds 30 deals, and installs `Sales Dashboard`
  + `Win Loss Analysis` + `Forecast` dashboards (LatticeQL widgets).
  Documents the widget JSON via `num()` / `bar()` / `donut()`
  builder helpers.

### Known follow-ups
- **task-257 + task-259 — page split + TableGrid split.** Both
  TIMEOUTed on the bot (1115-line and 993-line files are too big
  for one worker session). Partial work is in `git stash`.

## v0.29 — 2026-05-08
- **Per-table default view, server-side (V37).** Clicking a view now flags
  it as the table's default via a new `is_default boolean` column on
  `public.table_views`, enforced by a partial unique index
  `WHERE is_default` so exactly one default exists per (workspace, table).
  An atomic `SECURITY DEFINER` SQL helper
  `set_table_default_view(workspace_id, table_id, view_name)` clears the
  current default and sets the target in one call, validating the target
  is a user view (not `__schema__`/`__order__`). Avoids the cycle a back-FK
  on `public.tables.default_view` would have introduced.
- **New endpoint** — `PUT /api/v1/tables/{id}/default-view` body
  `{name}` → returns `{default_view}`. Wired into `TableResponse`
  alongside `columns`, so the FE gets the resume hint with the table fetch
  (no extra round-trip).
- **FE resume order**: URL `?view=` → `table.default_view` → implicit
  Table → first user view. Match runs against a candidate set that
  *includes* the implicit Table view, so a saved `default_view='Table'`
  resumes correctly when no user "Table" view exists.
- **FE click**: writes via `PUT /default-view`. Skipped for the implicit
  Table tab (no DB row to flag) — clicking it leaves the previous default
  unchanged.
- **Per-user UI config (V36).** New `config jsonb NOT NULL DEFAULT '{}'`
  column on `public.user_info`. New `PATCH /api/v1/login/me/config`
  shallow-merges supplied keys (top-level `null` removes a key) and
  returns the new full blob. `MeResponse` carries `config` so the FE
  hydrates without an extra request.
- **`darkMode` is now cross-device.** `frontend/src/lib/stores/settings.store.ts`
  hydrates from `/me` on auth, mirrors changes to localStorage as a
  fast-paint cache, and debounces a `PATCH /me/config` for any drift
  from the last-known server value. `speechLang` and notification
  settings stay in localStorage (single-device, no need to round-trip).
- **Schema test additions** — `public.user_info.config jsonb`,
  `public.table_views.is_default boolean`, and the
  `table_views_one_default` partial unique index. The previously-forbidden
  V34 entries for `is_default`/`table_views_one_default` are removed.

## v0.28 — 2026-05-02
- **Fix V34 trigger blocking table delete (V35).** The V34
  `trg_table_views_prevent_schema_delete` trigger refused to delete the
  `__schema__` row even when the deletion was a CASCADE from a parent
  `tables` row, making `DELETE /tables/{id}` 500. Drop the trigger via
  V35; the API layer already enforces "users can't delete __schema__"
  by rejecting reserved names in `DELETE /views/{name}`.
- **Fix FE view switcher.** `routes/[workspace_id]/[table_id]/+page.svelte`
  still read `$currentTable?.views` (the V33 inline JSONB array, gone
  after V34). Switched all 5 references to the new `$viewsStore` which
  the table-load flow populates. View tabs / switcher now show again.

## v0.27 — 2026-05-02
- **ECharts dashboard with JSON-described blocks.** Replaced
  `chart.js` + `svelte-chartjs` with Apache ECharts (`echarts ^5.6`).
  Each dashboard view's `config` is now `{layout, blocks}` where each
  block is one of:
  - `kind='chart'` — full ECharts `option` JSON with a `{$inject: 'rows'}`
    placeholder that the runtime replaces with `{source: rows}` (ECharts
    native dataset format).
  - `kind='number'` — single big number with `field` + `format`.
  - `kind='list'` — plain HTML table with `columns: [{key, label}]`.
- **New endpoint** — `POST /api/v1/tables/{tid}/views/{name}/blocks/{block_id}/query`.
  Replaces the v0.24 `/widgets/{widget_id}/query` path; same response
  shape `{rows: [...]}`.
- **Backend** — `models/view.py` adds discriminated block models
  (`ChartBlock` / `NumberBlock` / `ListBlock`). Dashboard router renames
  `widget_id` → `block_id`. CRM template seeder produces the new shape.
- **Frontend** — `lib/charts/EChart.svelte` (~30 LOC generic ECharts
  wrapper with ResizeObserver + theme integration), `lib/charts/inject.ts`
  (recursive `$inject` resolver). `lib/components/dashboard/blocks/`
  replaces `widgets/` (Block.svelte dispatcher + ChartBlock + NumberBlock
  + ListBlock). `DashboardView.svelte` simplified to iterate layout.
- **Breaking** — old widget shape no longer accepted. Only the CRM
  template's dashboard existed in the wild; it's regenerated by the new
  seeder.

## v0.26 — 2026-05-01
- **Simplify `table_views` (V34).** Drop V33's linked-list / `is_default` /
  `view_number` machinery. PK is now `(workspace_id, table_id, name)`.
  Single `type` column discriminates row purpose:
  - `type='schema'` (`name='__schema__'`) — config holds the column array,
    replacing `tables.columns`. Cannot be deleted (BEFORE-DELETE trigger).
  - `type='order'` (`name='__order__'`) — config holds the ordered name
    array; reorder = one UPDATE on the array.
  - `type='table' | 'kanban' | 'timeline' | 'dashboard'` — user-named view
    rows.
- **`tables` shrinks to identity-only.** `columns` JSONB column dropped.
- **One trigger replaces three** — `trg_table_views_prevent_schema_delete`
  refuses deletion of the schema row; `trg_tables_create_schema_and_order`
  auto-inserts both meta-rows on table create.
- **New endpoint** — `GET / PUT /api/v1/tables/{tid}/view-order`. PUT body
  is `{order: ["A","B"]}` and self-heals stale names against actual user
  views. Replaces V33's `/views/{name}/move`.
- **Backend** — `models/table_view.py`, `repository/table_view.py`,
  `router/api/tables.py` rewritten for the simplified shape. Column CRUD
  endpoints route through the schema row. `repository/table.py` keeps
  identity + index management; column ops moved to `TableViewRepository`.
- **Frontend** — `Table.views` removed (views are fetched separately).
  `lib/backend/views.ts` adds `fetchViewOrder` / `putViewOrder`. Store
  exposes `views`, `viewOrder` writables and per-view splice mutations
  (`createView` / `updateView` / `deleteView` / `reorderViews`).
- **Migration tests** updated for the new shape (PK, dropped columns,
  trigger names).

## v0.25 — 2026-05-01
- **`tables.views` JSONB → dedicated `public.table_views` table.** Every
  view is now a row with its own audit, locking, and indexing instead of
  living inside a JSONB array. Per-view invariants enforced in the
  database:
  - Partial unique index on `(workspace_id, table_id) WHERE is_default`
    → exactly one default per table.
  - `BEFORE DELETE` trigger refuses to remove `is_default=true`
    → at least one view per table.
  - `AFTER INSERT ON tables` trigger auto-creates the default Table view.
  - `next_view_id` self-FK (DEFERRABLE INITIALLY DEFERRED) for
    linked-list ordering walked by the FE.
- **Migration V33** — schema + 3 triggers + RLS policy + backfill from
  existing `tables.views` JSONB; drops the old column.
- **Backend rewrite** — new `models/table_view.py`, `repository/table_view.py`
  (list_ordered / get_by_name / create / update / delete / move).
  `router/api/tables.py` view endpoints route through the new repo.
  PM/CRM template seeders update the trigger-created default view in
  place rather than inserting their own "Table" view.
- **New endpoint** — `PUT /api/v1/tables/{tid}/views/{name}/move` body
  `{after_name: string|null}` for atomic reorder (null = head).
- **One-view-one-JSON CRUD shape** — every per-view endpoint returns
  exactly one view dict (or 204 on DELETE), so the FE can patch its
  local state instead of refetching. (FE client wiring is a follow-up.)
- **LatticeQL → pure-Python git dep.** Switched `lattice-ql` from a
  vendored wheel (`/app/vendor/lattice_ql-0.3.0-...whl`) to a pinned
  git install: `lattice-ql @ git+https://github.com/latticeCast/LatticeQL@v0.2.0`.
  Upstream is pure Python (hatchling) — no Rust toolchain in the backend
  image anymore. Backend Dockerfile gained `git` apt for the install.
  Backend adapter (`config/lattice_ql.py`) updated for the v0.2.0 API:
  `compile(lql, schema)` returns SQL string; adapter inlines `$1` as the
  workspace_id literal then runs the existing `_fix_table_name` rewrite.

## v0.24 — 2026-04-30
- **Dashboard view + CRM template**. New `dashboard` view type renders
  aggregates over rows via LatticeQL widget queries (number / bar / pie /
  line / list). New `POST /api/v1/tables/template/crm` seeds a CRM table
  with a default dashboard.
- **LatticeQL integration**. Backend imports the `lattice-ql` Python
  wheel from GitHub release (v0.3.3). New `config/lattice_ql.py` caches
  the per-workspace schema in Valkey (60s TTL).
- New widget query endpoint:
  `POST /api/v1/tables/{tid}/views/{name}/widgets/{wid}/query`.
- Frontend chart lib: `chart.js` via `svelte-chartjs`.
- Backend Dockerfile is now multi-stage: Rust toolchain in builder, slim
  Python in runtime.

## v0.23 — 2026-04-25
- **Role rebalance: `login_mgr` is now register/delete-only** — all other auth lookups go through the `app` role. Affected routes: `get_current_user`, `POST /password`, `GET /me`, `add_member`, `list_users`, `get_user`, `update_user` all dropped `login_session`. `create_user`, `delete_user`, OAuth `/{provider}/token` kept it. Rationale: once logged in, every API call runs with `app` permissions — `login_mgr` is only for PII-writing boundaries (register/delete).
- **Migration V32** — `GRANT SELECT ON auth.gdpr TO app` + `GRANT UPDATE (role) ON auth.users TO app` + default-privileges for future auth tables. Enables app to resolve users by email and admins to change user roles without `login_mgr`.
- **Browser test script** — `browser/` entrypoint now accepts an optional URL argument for screenshots (easier ad-hoc snapshots without editing scripts).
- **Skills — lint enforcement before commit**:
  - `developing-programming` v0.9.0: all lint runs inside Docker containers (FE `docker compose exec frontend npm run lint`, BE `uv run ruff`, PG `migration --test-only`). Local host has no Node/Python/sqlfluff.
  - `developing-svelte` v0.5.0: FE dev rule — `no-unused-vars` MUST be clean, `{@html}` must be sanitized, `// eslint-disable` is forbidden.

## v0.22 — 2026-04-23
- **FE auth simplified — one path, no build-time branch.** Dropped `VITE_AUTH_REQUIRED` from `vite.config.ts`; FE no longer reads `auth_required`. Login page always shows `user_name + password` inputs; OAuth (Authentik, Google) buttons kept as alternatives on the same card (code retained, not gated).
- **New BE endpoint `POST /api/v1/login/password`** — accepts `{user_name, password}`. In `AUTH_REQUIRED=false` mode: ignores password, resolves user by user_name or email, returns the user_id UUID as `access_token`. In `AUTH_REQUIRED=true` mode: returns 501 (clients should use OAuth). Relaxed `UserInfo.email` in auth responses from `EmailStr` to `str` to accommodate non-email handles.
- **Dead code removed** — `AppConfig` / `fetchAppConfig` in `frontend/src/lib/backend/auth.ts` (no callers).
- **Svelte logic split per skill** — extracted login orchestration from `login/+page.svelte`:
  - `frontend/src/lib/auth/validation.ts` — `USER_NAME_RE`, `validateUserName()` (pure TS, testable).
  - `frontend/src/lib/auth/login.svelte.ts` — `loginState` runes + `submit()` orchestration.
  - `.svelte` file now UI-only with `data-testid` on every interactive element (`login-userid`, `login-password`, `login-start`, `login-error`, `login-authentik`, `login-google`).

## v0.21 — 2026-04-15
- **GDPR-aware user schema split** — three tables with role-gated access:
  - `auth.users` (user_id UUID PK, role) — identity core
  - `auth.gdpr` (user_id FK, email UNIQUE, legal_name) — **PII, login_mgr only**. app role cannot read/write.
  - `public.user_info` (user_id FK, user_name VARCHAR(32) UNIQUE CHECK `^[a-z0-9][a-z0-9_-]{2,31}$`) — public handle only. No display_name.
- Benefits: right-to-be-forgotten = single `DELETE FROM auth.gdpr`; portability = single SELECT; data minimization (app layer cannot leak PII — compile-time enforcement).
- **V5 cleanup** — removed user_info creation from V5 (was creating the table too early with wrong schema).
- **V10 rewrite** — creates `public.user_info` + `auth.gdpr`, populates from legacy users columns.
- **V20, V23 deleted** — display_id→user_name rename now happens natively in V10.
- **V26 simplified** — only moves `auth.users` (user_info stays in public, gdpr already in auth).
- **`migrate.py` SQL splitter upgraded** — now tracks `--` line comments, `/* */` block comments, `'...'` strings, `"..."` identifiers, and `$$..$$` dollar-quotes. No more false splits on `;` inside comments/strings.
- **SECURITY DEFINER functions for per-column indexes** — `create_row_data_index()` / `drop_row_data_index()` in V27. App calls via `SELECT` — no DDL privileges granted to app_user. Replaces the ad-hoc `GRANT CREATE` / `ALTER TABLE OWNER` hacks.
- **Cleaned up `get_rls_session`** — removed try/except workaround. Relies on asyncpg pool's DISCARD ALL on connection return.
- **Backend refactor**: split `UserRepository` into `UserRepository` (app) + `GdprRepository` (login). `bootstrap_user()` helper coordinates the three-table create across two sessions. Auto-create in no-auth mode disabled (raises 403) to eliminate multi-worker race.
- **checksums.txt** regenerated (27 files; V20/V23/V28 removed, V10 rewritten).
- **Skill `developing-db-sql` updated** — documents alignment enforcement.

## v0.20 — 2026-04-15
- Migration SQL now **must** pass SQLFluff lint — no more "warning only" bypass. `step_lint` returns False on violations, blocking the flow before any DB is touched.
- `.sqlfluff` config: `max_line_length = 80`, strict defaults, `references.keywords` excluded (existing schema uses `name` / `role` / `email` as column names). `CREATE TABLE` column alignment is **enforced** via `align_within = create_table_statement` — `sqlfluff fix` auto-aligns.
- Auto-fixed + manually split 300+ violations across all V*.sql — long lines wrapped to ≤80 char, `CHECK (...)` expressions split onto multiple lines, `ALTER TABLE ... CONSTRAINT` / `CREATE INDEX` broken at logical points.
- Added missing `AS` aliases to `INSERT ... SELECT CASE END` column expressions (V5, V6, V10) — AL03.
- **Migration tracking moved to `private` schema** (DBA-only) — app/login roles cannot see or touch `schema_migrations`. New `V1__init_migration_tracking.sql` bootstraps the tracking table.
- **V2 now uses `ALTER DEFAULT PRIVILEGES FOR ROLE dba`** — all future tables created by any dba-role user automatically inherit app/login grants. Makes post-hoc regrant redundant.
- **Deleted V28__regrant_permissions.sql** — superseded by explicit `FOR ROLE dba` default privileges.
- Migrate runner reports current DB version + pending count at start of apply: `DB at V30 (29 applied), 0 pending`.
- **Checksum integrity** (SHA-256): committed `migration/checksums.txt` is the source of truth. `migrate.py` verifies every V*.sql against it before apply. Regenerate via `python migrate.py --hash` after editing any migration.
- DB-side checksum: `private.schema_migrations.checksum` column tracks applied file hashes. Mismatch between stored (DB) and current (disk) aborts apply — prevents tampered migrations from silently reapplying.
- Fix `storage.py`: `get_user_prefix(user)` treated `user.user_id` as string (legacy email PK). Now handles UUID — `str(user.user_id).replace("-", "")[:20]`. Upload/download were crashing with `AttributeError: UUID has no attribute 'replace'`.

## v0.19 — 2026-04-15
- **Async-native S3: boto3 → aioboto3.** No more `asyncio.to_thread` wrappers — aioboto3 is native async, can never block the event loop even if a dev forgets to wrap a call.
- `config/storage.py`: `get_s3_client()` (singleton sync) → `s3_client()` (async context manager). Usage: `async with s3_client() as s3: await s3.put_object(...)`.
- `rows.py` + `storage.py`: rewrote all 13 S3 call sites to `async with s3_client() as s3: await s3.xxx(...)` pattern.
- New skill `developing-fastapi` (v0.1.0): async-by-default rules, anti-patterns, Uvicorn worker guidance — documents the blob-blocking root cause.
- `pyproject.toml`: dep `boto3` → `aioboto3`.

## v0.18 — 2026-04-15
- **Root cause fix: blocking S3/MinIO calls froze the entire event loop.** Single large upload/download made the whole backend appear dead — other users couldn't list tables or fetch data until the blob op finished.
- Wrapped all boto3 calls in `asyncio.to_thread(...)` — both `rows.py` doc endpoints and `storage.py` file endpoints (put/get/list/head/delete).
- Composite PK on `tables`: `(workspace_id, table_id)` — allows same table name in different workspaces (V29).
- RLS policies handle empty `app.current_user_id` via `NULLIF` — no more `::uuid` crashes on missing context (V30).
- Cleanup: removed RLS debug logs and unnecessary `finally: rollback()` workarounds in session dependencies — root cause was blob blocking, not session leaks.
- Uvicorn: `--workers 4` → single worker (async handles I/O concurrency, avoids race on auto-user-create).
- V28: re-grant permissions on tables created by later migrations (V1's `GRANT ON ALL TABLES` only covered pre-existing tables).

## v0.17 — 2026-04-14
- Migration runner: lint (SQLFluff) → test (temp DB + schema/RLS verify) → apply
- DBA credentials removed from `.env` — hardcoded in docker-compose only, backend never sees them
- Backend no longer runs migrations — separate `migration` container with `--profile migration`
- Migration files renamed to Flyway format (`V1__name.sql`)
- Fixed migration ordering bugs: 0018/0020/0021 referenced columns from later migrations
- Removed `setup-db.sh` — roles/schemas bootstrapped via `V1__bootstrap_roles.sql`
- Removed Atlas dependency (lint is Pro-only since v0.38)

## v0.16 — 2026-04-13
- PG schema-based permission model: `public` (data), `auth` (users), `private` (internal)
- PG native roles: `dba` (DDL all schemas), `app` (CRUD public, SELECT auth), `login_mgr` (CRUD auth)
- Separate DB engines per role: dba for migrations, app for API, login_mgr for auth
- Row-Level Security on `rows` + `tables` — workspace membership enforced at DB level
- `users` + `user_info` moved to `auth` schema
- PG native logging enabled (`log_statement=all`, connections/disconnections)
- `init-roles.sh` for new DB setup, migration SQL for existing DBs

## v0.15 — 2026-04-12
- New column type `doc` — read-only cell, auto-creates MinIO .md on row insert (Layer 1)
- PM template uses `type="doc"` instead of `type="url"` for Doc column
- Fix: column dropdown menu hidden behind doc cell buttons (z-index stacking context)
- Theme manager exports reactive `T` proxy — components use `T.cardBg` directly
- Fix: sidebar menu stays open on table click (navigate without closing)
- Fix: Table view grouping — shared `GroupBySelector` component with Kanban
- Browser container: `network_mode: host` + `user: 1000:1000` for Playwright snapshots
- Skills: all API paths updated `/api/` → `/api/v1/`

## v0.14 — 2026-04-11
- Fix: duplicate row on create — `session.add(detached)` caused second INSERT instead of UPDATE
- Fix: Doc column cell paths migrated from UUID-based to string table_id (one-time script)

## v0.13 — 2026-04-11
- `table_id` is now string PK (= table name, always lowercase) — no more UUIDs for tables
- API prefix changed from `/api/` to `/api/v1/`
- Removed `table_name` column — `table_id` IS the name
- Doc column is first column (position 0) in all templates
- Default table template: Doc + Title + Description

## v0.12 — 2026-04-09
- Simplified naming: `workspace_name` (no display_id), `user_name` (unique)
- Added `doc` column type — inline markdown editor backed by MinIO
- `url` column: external links open new tab, internal paths navigate to `/{path}`
- Title is plain text cell — no special click behavior
- Every table has at least 1 Table view (auto-created, can't delete last)
- Add Row: optimistic UI, instant inline row creation
- Add View: full-width panel overlay
- PM template Status choices: todo, in_progress, testing, debugging, review, done, merged

## v0.11 — 2026-04-07
- `row_number` BIGSERIAL PK per table (replaces UUID `row_id`)
- Composite PK `(table_id, row_number)`, auto-increment via PG trigger
- UUID-based users: `user_id` UUID PK, `user_info` for display_id/email/name (GDPR)
- Workspace UUID PK + `workspace_name`
- Rows default sort: desc (newest first)
- `filter_json` query param for server-side JSONB filter
- Token resolution: UUID → display_id → email
- Remove Key column — use `type-row_number` as ticket ID

## v0.10 — 2026-04-05
- Skills: claude-bot plan | prepare | running split
- Skills: `pm_tools.sh` shared bash helpers
- Skills: orchestrator pure rule-based (no LLM), worker bash infra + LLM code
- Orchestrator: recovery of orphaned in_progress tickets on startup
- Orchestrator: poll PM status for worker completion (no trigger files)
- Worker: bash handles PM+git, LLM only writes code
- Architecture docs: `llm.arch.airtable.md` (Layer 1) + `llm.arch.pm.md` (Layer 2)

## v0.9 — 2026-04-04
- Perf: batch docs-exist endpoint (75 HEAD requests → 1 S3 list call)
- Non-blocking doc flag loading — page renders immediately, doc icons appear async

## v0.8 — 2026-04-03
- Skills: auto-create test ticket per story in planning
- Skills: test-tagged tickets run Playwright snapshot instead of unit tests
- Skills: worker rule — continuously update ticket doc in MinIO as work journal
- Skills: planning writes design content to epic/story/issue docs after approval
- Skills: enforce `in_progress` status update as first worker action
- Default time rule: tickets without dates default to today
- CLAUDE.md: skill version bump rule + submodule commit rule

## v0.7 — 2026-04-01
- Issue Detail View: full-page ticket at `/<workspace>/<table>/<row_id>`
- Marked HTML rendering with edit/preview toggle
- Breadcrumb navigation: user / workspace / project / key (clickable)
- TableGrid: Key/Title click navigates to issue detail
- RowExpandPanel: "Open full page" link
- PM template default view config: Table sorted by Start Date desc
- Sidebar UX: ☰/« toggle moved into blue top bar (no floating button)
- Dark mode: toggle in settings, dark class on html/body, dark sidebar/nav
- QA: Playwright snapshot tests for all views (table, kanban, timeline, expand, detail, template)

## v0.6 — 2026-03-30
- Nginx reverse proxy: FE + BE on single port (13491)
- OpenAPI docs moved under `/api/` prefix
- Worker hierarchy: epic → story → issue branching (issue worktree from story branch)
- Worker docs: continuous MinIO doc updates as work journal
- PM Doc column (type=url) auto-populated with MinIO path on row creation
- Split doc editor: markdown textarea + marked HTML preview with Tailwind prose
- Doc icon indicator in TableGrid
- Enforce epic→story→issue hierarchy in planning skills
- Story branch management + auto-cascade (children merged → parent merged)
- `immutable_timestamp()` PG function for date column B-tree indexes
- Ports from .env: NGX_PORT=13491, NGX_PORT=13492

## v0.5 — 2026-03-29
- Workspace-based multi-tenant architecture (workspaces, workspace_members, shared access)
- Columns stored as JSONB in tables (no separate columns SQL table)
- Row data in `row_data` JSONB with `created_by`/`updated_by` audit fields
- Per-column PG indexes (B-tree for number/date, GIN for select/tags/text) auto-managed on column create/delete
- Customizable views: Table (default), Kanban (drag-and-drop), Timeline/Gantt (date bars)
- PM template with auto-generated ticket keys (e.g. SA-1), epic/story/task/bug hierarchy
- Ticket doc system: each ticket has a markdown doc in MinIO, auto-generated templates, hierarchy links
- Doc tab in row expand panel with markdown editor + preview
- View switcher (Table | Sprint Board | Roadmap) with per-view config
- Template gallery UI for creating PM projects
- Frontend URL pattern: `/<workspace_id>/<table_id>`
- Auto-create default workspace on user registration
- Skills integration: developing-project-management, developing-programming with LatticeCast PM status updates
- Auto-cascade: all children merged → parent auto-merged

## v0.4 — 2026-03-22
- Airtable-like flexible schema with JSONB rows
- Table CRUD with columns (text, number, date, select, tags, checkbox, url)
- Inline cell editing, column resize, sort/group/filter toolbar
- Import/export (CSV, JSON, template)
- Row expand panel, context menu, column header dropdown
- Blue/white theme overhaul
- Typed cell rendering (colored badges, tag pills, toggles, links)
- OAuth login (Google, Authentik) with PKCE
- MinIO file storage with UUID-prefix isolation
- Admin user management API
