# Changelog

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
