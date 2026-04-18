# LLM Context - Airtable Core (Layer 1)

The generic table engine. Everything here works for ANY table — PM, CRM, or custom.

## Schema

```sql
-- Tables with embedded column definitions + view configs
public.tables (
    workspace_id  UUID FK,
    table_id      VARCHAR,           -- string PK = table name, always lowercase
    columns       JSONB DEFAULT '[]',  -- [{column_id, name, type, options, position}]
    views         JSONB DEFAULT '[]',  -- [{name, type, config}]
    timestamps,
    PK (workspace_id, table_id)
)

-- Rows with flexible JSONB data
public.rows (
    workspace_id UUID,
    table_id     VARCHAR,
    row_number   BIGINT,               -- auto-set by trigger: MAX(row_number)+1 per (workspace_id, table_id)
    row_data     JSONB DEFAULT '{}',   -- {"col_id": value, ...}
    created_by   UUID FK auth.users,
    updated_by   UUID FK auth.users,
    timestamps,
    PK (workspace_id, table_id, row_number),
    FK (workspace_id, table_id) REFERENCES tables ON DELETE CASCADE
)
```

RLS enabled on both tables — policies check workspace membership via `current_setting('app.current_user_id')`.

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
- All partial: `WHERE workspace_id = '{uuid}' AND table_id = '{name}'`

## Views

Stored in `tables.views` JSONB. Every table has at least 1 Table view (auto-created).

| Type | Component | Config |
|------|-----------|--------|
| `table` | TableGrid | sort, filter, group, hiddenCols, columnWidths |
| `kanban` | KanbanBoard | group_by, card_fields, sort |
| `timeline` | TimelineView | start_col, end_col, color_by, group_by |

## Default Template

New table without template gets: Doc (doc) + Title (text) + Description (text) + 1 Table view.
`doc` column is system-managed: on row insert, backend auto-creates an empty `.md` at MinIO key `{workspace_id}/{table_id}/{row_number}.md` and writes the path into the cell. Users cannot edit `doc` cell values directly.

## URL Pattern

```
/<workspace_id>/<table_id>              → table view
/<workspace_id>/<table_id>/<row_number> → row detail
```

`table_id` is the lowercase table name (string). `workspace_id` is UUID.
