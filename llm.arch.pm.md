# LatticeCast — PM Layer

PM is Layer 2: a seeded table schema plus conventions on top of the generic
table engine. It does not have separate row, view, authorization, or storage
models.

## Template

`POST /api/v1/tables/template/pm` creates the PM table through the shared PG
template dispatcher. The seed defines ticket-oriented columns such as Title,
Doc, Type, Status, Priority, Assignee, dates, estimate, tags, description, and
Parent, plus Kanban and Timeline views.

The migration seeder is the source of truth for exact column order, choices,
colors, and default view. Do not duplicate that configuration in frontend code
or this onboarding document.

## Ticket Conventions

- Ticket kinds are epic, story, task, and bug.
- Parent stores the parent row's per-table numeric `row_id`.
- Display keys are derived from ticket type and `row_id`; there is no separate
  global ticket identity.
- Title stays short; detailed requirements, decisions, and work notes belong in
  the Markdown document.
- The main document object key is
  `{workspace_id}/{table_id}/{row_id}.md`.

Typical hierarchy:

```text
Epic
  `-- Story
        |-- Task
        `-- Bug
```

## Workflow Boundary

Status, hierarchy, and parent progression are conventions consumed by agents or
automation. The core backend stores the values and renders the views; it does
not introduce a PM-only CRUD path for every workflow transition.

Generic Layer-1 behavior includes column/row/view CRUD, filtering, grouping,
Kanban drag-and-drop, Timeline rendering, import/export, and document access.

## Main Files

| Concern | Source |
|---|---|
| PM template SQL | template functions under `migration/V*.sql` |
| Template endpoint | `backend/src/router/api/tables/templates.py` |
| Row/doc behavior | `backend/src/router/api/rows.py` |
| Table UI | `frontend/src/routes/[workspace_id]/[table_id]/+page.svelte` |
| Kanban/Timeline | `frontend/src/lib/components/table/` |
| Project automation skill | `.agent-skills/developing/project-management/SKILL.md` |

When changing the PM template, update the SQL seeder and its template E2E test;
keep generic table code generic.
