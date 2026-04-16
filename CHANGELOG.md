# Changelog

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
- Ports from .env: BACKEND_PORT=13491, FRONTEND_PORT=13492

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
