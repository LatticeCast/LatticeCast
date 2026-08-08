# LLM Context - PM System (Layer 2)

Built ON the Airtable core. PM is just a template + conventions — no special code paths.

## PM Template

`POST /api/v1/tables/template/pm` creates a table with these columns:

| Position | Column | Type |
|----------|--------|------|
| 0 | Title | text (short summary) |
| 1 | Doc | doc (read-only, auto-creates MinIO .md on row insert) |
| 2 | Type | select (epic/story/task/bug) |
| 3 | Status | select (todo/in_progress/testing/debugging/review/done/merged) |
| 4 | Priority | select (critical/high/medium/low) |
| 5 | Assignee | text |
| 6 | Start Date | date |
| 7 | Due Date | date |
| 8 | Estimate | number |
| 9 | Tags | tags |
| 10 | Description | text |
| 11 | Parent | text (row_id of parent) |

Available views: implicit Table (rendered from `tables.config`) + Sprint Board
(Kanban by Status) + Roadmap (Timeline). The seeder inserts only the Kanban
and Timeline rows, sets Sprint Board as `default_view`, and leaves the
implicit Table without a `table_views` row.

## Hierarchy

```
Epic (type=epic, parent=null)
└── Story (type=story, parent=epic_rn)
    └── Task/Bug (type=task/bug, parent=story_rn)
```

- Workers only implement tasks/bugs
- The core API stores hierarchy values but does not cascade statuses.
- Agentic-hive/project automation may advance parents after checking children.

## Ticket ID

`<type>-<row_id>` — e.g. `task-42`, `story-15`, `bug-7`. No Key column.

## Ticket Doc

Each ticket has a markdown doc in MinIO at `{workspace_id}/{table_id}/{row_id}.md`.

- **Title is SHORT** (max 80 chars, one line)
- **Doc has ALL detail** (implementation instructions, files, decisions, work log)
- Workers READ doc first before implementing

## Status Flow

```
todo → in_progress → testing → review → done
                       ↓
                    debugging → testing (loop)

Parent status changes are performed by automation, not by a PM-specific backend route.
```

## What's NOT PM-specific

These are Layer 1 (Airtable core), not PM:
- Column CRUD, row CRUD, view CRUD
- Sort, filter, group, search
- Import/export
- Kanban drag-and-drop
- Timeline date bars
- Markdown rendering
- URL resolution
