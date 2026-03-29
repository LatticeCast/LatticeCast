# LatticeCast

Self-hosted Airtable + Jira. Flexible tables with JSONB, customizable views (Table, Kanban, Timeline), and built-in project management.

## Features

- **Flexible Schema** — create columns of any type (text, number, date, select, tags, checkbox, url), all stored as JSONB
- **Workspaces** — multi-user, shared access with owner/member roles
- **Views** — Table (spreadsheet), Kanban (drag-and-drop), Timeline/Gantt (date bars), all customizable
- **PM Template** — Jira-like project management with epic/story/task/bug hierarchy, auto-generated ticket keys
- **Per-column Indexes** — auto-managed PG B-tree (number/date) and GIN (select/tags) indexes
- **Ticket Docs** — each ticket has a markdown doc in MinIO with auto-generated templates and hierarchy links
- **Auto-cascade** — all children merged → parent auto-merged
- **Import/Export** — CSV, JSON, templates
- **OAuth** — Google, Authentik with PKCE

## Data Model

```
workspaces       → multi-user (workspace_id = owner email)
workspace_members → membership + role
tables           → columns JSONB + views JSONB
rows             → row_data JSONB + created_by/updated_by
MinIO            → ticket docs as {user}/{workspace}/{table}/{row}.md
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript, Vite 7 |
| Backend | FastAPI, Python 3.12, Uvicorn |
| Database | PostgreSQL 18, JSONB + auto-managed indexes |
| Cache | Valkey 8 |
| Storage | MinIO (S3-compatible) — ticket docs |
| Auth | Google OAuth, Authentik |

## Quick Start

```bash
docker compose up -d
# Frontend: http://localhost:13491
# Backend:  http://localhost:13491/api/
# API docs: http://localhost:13491/api/docs
```

## URL Pattern

```
/<workspace_id>/<table_id>          — table detail (Table/Kanban/Timeline views)
/<workspace_id>/<table_id>?view=X   — specific view
/tables                             — tables list
```

## PM Workflow

```
1. Create PM project from template (epic/story/task/bug + Kanban + Timeline views)
2. Create tickets → auto-generated keys (e.g. SA-1, SA-2)
3. Developer picks ticket → branch → implement → test → merge
4. Status auto-updates: todo → in_progress → testing → review → merged
5. All children merged → parent auto-merged
6. Ticket docs in MinIO track specs/notes per ticket
```

## Views

All views render the same JSONB data — just different presentations:

| View | Description |
|------|-------------|
| **Table** | Spreadsheet grid with sort/group/filter/search |
| **Kanban** | Cards grouped by any select column, drag-and-drop |
| **Timeline** | Horizontal date bars, configurable start/end/color/group |
