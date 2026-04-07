# LLM Context - Airtable Core (Layer 1)

The generic table engine. Everything here works for ANY table — PM, CRM, or custom.

## Schema

```sql
-- Tables with embedded column definitions + view configs
tables (
    workspace_id  UUID FK,
    table_id      UUID PK,
    table_name    VARCHAR UNIQUE(workspace_id, table_name),
    columns       JSONB DEFAULT '[]',  -- [{column_id, name, type, options, position}]
    views         JSONB DEFAULT '[]',  -- [{name, type, config}]
    timestamps
)

-- Rows with flexible JSONB data
rows (
    table_id    UUID FK (CASCADE),
    row_number  BIGINT (auto-increment per table, PG trigger),
    row_data    JSONB DEFAULT '{}',  -- {"col_id": value, ...}
    created_by  UUID FK,
    updated_by  UUID FK,
    timestamps
    PK (table_id, row_number)
)
```

## Column Types

| Type | JSONB Value | Index |
|------|-------------|-------|
| `text` | string | GIN |
| `number` | number | B-tree (::numeric) |
| `date` | string (ISO) | B-tree (immutable_timestamp()) |
| `select` | string | GIN |
| `tags` | string[] | GIN |
| `checkbox` | boolean | GIN |
| `url` | string | GIN |
| `doc` | (MinIO markdown) | — |

## Per-Column Indexes

Auto-managed on column create/delete:
- Number/Date → B-tree expression index
- Select/Tags/Text → GIN index
- All partial: `WHERE table_id = '{uuid}'`

## Views

Stored in `tables.views` JSONB. Every table has at least 1 Table view (auto-created).

| Type | Component | Config |
|------|-----------|--------|
| `table` | TableGrid | sort, filter, group, hiddenCols, columnWidths |
| `kanban` | KanbanBoard | group_by, card_fields, sort |
| `timeline` | TimelineView | start_col, end_col, color_by, group_by |

## Default Template

New table without template gets: Doc (url) + Title (text) + Description (text) + 1 Table view.

## URL Pattern

```
/<workspace_name>/<table_name>              → table view
/<workspace_name>/<table_name>/<row_number> → row detail
```

Both UUID and name work (resolver: UUID → name → case-insensitive).
