# LatticeCast

Airtable-like project management system with flexible, user-defined schemas.

## Core Concept

Users can create custom tables and define columns of any type (text, number, date, select, tags, checkbox, url, etc.). All row data is stored as PostgreSQL JSONB — no DDL changes needed when users modify their schema. Column definitions are embedded in the table record as JSONB, not a separate SQL table.

## Data Model

```
workspaces      → multi-user workspaces (workspace_id = owner email)
workspace_members → user membership + role per workspace
tables          → user-created tables (name, workspace_id, columns JSONB)
rows            → actual data as JSONB, keyed by column ID
```

### Schema

```sql
-- Users (email is identity, same user regardless of login method)
CREATE TABLE users (
    user_id     VARCHAR PRIMARY KEY,  -- email
    name        VARCHAR NOT NULL DEFAULT '',
    role        VARCHAR NOT NULL DEFAULT 'user',
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

-- Workspaces (auto-created per user on registration)
CREATE TABLE workspaces (
    workspace_id  VARCHAR PRIMARY KEY,  -- email (owner's user_id for default workspace)
    name          VARCHAR NOT NULL,
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);

-- Workspace membership
CREATE TABLE workspace_members (
    workspace_id  VARCHAR REFERENCES workspaces(workspace_id),
    user_id       VARCHAR REFERENCES users(user_id),
    role          VARCHAR NOT NULL DEFAULT 'member',  -- 'owner' | 'member'
    PRIMARY KEY (workspace_id, user_id)
);

-- Tables with embedded column definitions
CREATE TABLE tables (
    table_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  VARCHAR NOT NULL REFERENCES workspaces(workspace_id),
    name          VARCHAR NOT NULL,
    columns       JSONB NOT NULL DEFAULT '[]',  -- [{id, name, type, options, position}]
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);

-- Row data (SSOT)
CREATE TABLE rows (
    row_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id    UUID REFERENCES tables(table_id) ON DELETE CASCADE,
    row_data    JSONB NOT NULL DEFAULT '{}',  -- {"col_id_1": "value", "col_id_2": 42}
    created_by  VARCHAR NOT NULL DEFAULT '',
    updated_by  VARCHAR NOT NULL DEFAULT '',
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
```

### Design Decisions

- **Column IDs as JSONB keys** — renaming a column doesn't touch row data
- **Columns in `tables.columns` JSONB** — no separate `columns` table, no DDL on column changes
- **Column `type` drives frontend** — rendering, validation, and sorting
- **Workspace-based access control** — tables belong to workspaces, not individual users
- **Single `rows` table** — no per-user-table DDL, all data is SSOT in JSONB
- **Fully qualified PKs** — `workspace_id`, `table_id`, `row_id`, `user_id` (not bare `id`)

### Column Types

| Type | JSONB Value | Example |
|------|-------------|---------|
| `text` | string | `"hello world"` |
| `number` | number | `42` |
| `date` | string (ISO) | `"2026-03-20"` |
| `select` | string | `"todo"` |
| `tags` | array of strings | `["bug", "urgent"]` |
| `checkbox` | boolean | `true` |
| `url` | string | `"https://..."` |

### Query Examples

```sql
-- Filter rows where status = "done"
SELECT * FROM rows WHERE row_data @> '{"col_status_id": "done"}';

-- Filter rows where priority > 3 (cast from JSONB)
SELECT * FROM rows WHERE (row_data->>'col_priority_id')::int > 3;

-- Check if a field exists
SELECT * FROM rows WHERE row_data ? 'col_notes_id';
```

## Views

Since all data lives in JSONB, every view is just a different query + frontend rendering on the same SSOT — no schema changes needed. Filtering is applied at the application level.

| View | Description | Query Pattern |
|------|-------------|---------------|
| **Table** | Spreadsheet grid | `SELECT *` |
| **Kanban** | Cards grouped by status | `GROUP BY row_data->>'col_status'` |
| **Timeline / Gantt** | Date-based horizontal bars | `ORDER BY (row_data->>'col_date')::date` |
| **Calendar** | Monthly/weekly date view | `WHERE date BETWEEN $1 AND $2` |
| **Grouped Table** | Rows grouped by any field | `GROUP BY row_data->>'col_any'` |
| **Gallery** | Card grid (image/summary) | `SELECT *` with card layout |

## Project Management Use Case

The system is general-purpose (like Airtable), but a key built-in use case is **project management with Git integration**.

### Git Sync

The PM table view automatically syncs with Git repositories to keep ticket status up to date:

- **`git fetch`** — periodically fetches remote branches to detect activity
- **Branch → Ticket mapping** — branches follow a naming convention so the system can parse and link them to rows (tickets)
- **Auto-update status** — when a branch is merged, the corresponding ticket status is updated automatically

### Branch Naming Convention

```
<type>/<ticket-id>/<short-description>

Examples:
  feat/PROJ-42/add-user-profile
  fix/PROJ-108/login-redirect-bug
  chore/PROJ-15/update-deps
```

- `<ticket-id>` maps to a row ID or a human-readable ticket key in the PM table
- The system parses branch names to match tickets and track:
  - Branch exists → ticket is "in progress"
  - Branch merged → ticket is "done"
  - No branch → ticket is "todo"

### OpenAPI Integration

The PM table view fetches `openapi.json` from connected services to:

- Display available API endpoints alongside tickets
- Track which endpoints are implemented (branch merged) vs. in progress
- Link tickets to specific API routes

### Workflow

```
1. Create ticket in PM table (row with status, assignee, etc.)
2. Developer creates branch: feat/PROJ-42/add-user-profile
3. System detects branch via git fetch → status auto-updates to "in progress"
4. Developer merges branch
5. System detects merge → status auto-updates to "done"
6. PM table view shows openapi.json endpoints with ticket status
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL 18, JSONB + GIN |
| Cache | Valkey 8 |
| Storage | MinIO (S3-compatible) |
| Auth | Google OAuth, Authentik |