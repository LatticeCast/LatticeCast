# Changelog

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
