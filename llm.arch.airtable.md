# LLM Context - Airtable Core (Layer 1)

The generic table engine. Everything here works for ANY table — PM, CRM, or custom.

## Schema (V34)

Three tables. `tables` is identity only; everything *about* a table — its
columns, its view-display order, and its individual views — lives as rows
in `public.table_views` discriminated by a `type` column.

```sql
-- Identity only
public.tables (
    workspace_id UUID FK,
    table_id     VARCHAR,         -- string PK = table name, always lowercase
    timestamps,
    PK (workspace_id, table_id)
)

-- One row per piece of metadata. `type` decides what `config` means.
--   type='schema' (name='__schema__'): config = column array
--   type='order'  (name='__order__'):  config = ordered name array
--   type='table' | 'kanban' | 'timeline' | 'dashboard' (user-given names):
--                                       config = view-specific config
public.table_views (
    workspace_id UUID,
    table_id     VARCHAR,
    name         VARCHAR,
    type         VARCHAR,
    config       JSONB,
    created_by   UUID FK auth.users,
    updated_by   UUID FK auth.users,
    timestamps,
    PK (workspace_id, table_id, name),
    FK (workspace_id, table_id) REFERENCES tables ON DELETE CASCADE
)

-- Rows with flexible JSONB data
public.rows (
    workspace_id UUID,
    table_id     VARCHAR,
    row_number   BIGINT,           -- auto: MAX+1 per (workspace_id, table_id)
    row_data     JSONB DEFAULT '{}',
    created_by   UUID FK auth.users,
    updated_by   UUID FK auth.users,
    timestamps,
    PK (workspace_id, table_id, row_number),
    FK (workspace_id, table_id) REFERENCES tables ON DELETE CASCADE
)
```

RLS enabled on `tables`, `table_views`, `rows` — policies check workspace
membership via `current_setting('app.current_user_id')`.

Two triggers enforce table_views invariants:
- `BEFORE DELETE ON table_views` refuses removal of `__schema__` rows
  → every table always has columns.
- `AFTER INSERT ON tables` inserts `__schema__` (empty array) and
  `__order__` (empty array) automatically → table-create is one INSERT.

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

Auto-managed on column create/delete (column ops route through the
`__schema__` row's config):
- Number/Date → B-tree expression index
- Select/Tags/Text → GIN index
- All partial: `WHERE workspace_id = '{uuid}' AND table_id = '{name}'`

## Views

Each user view is one row in `public.table_views` with `type ∈ {table,
kanban, timeline, dashboard}` and a user-chosen `name`.

| Type | Component | Config |
|------|-----------|--------|
| `table` | TableGrid | sort, filter, group, hiddenCols, columnWidths |
| `kanban` | KanbanBoard | group_by, card_fields, sort |
| `timeline` | TimelineView | start_col, end_col, color_by, group_by |
| `dashboard` | DashboardView | layout, widgets (each widget has `lql` LatticeQL query — see `llm.arch.dashboard.md`) |

The default rendering of a table is the schema row interpreted as a Table
view (FE reads `__schema__`'s column array). Users can additionally save
custom Table views (`type='table'`) with sort/filter/group settings.

Display order is the `__order__` row's config — a `string[]` of view
names. Reorder is one PUT replacing the whole array.

## Default Template

New table without template gets: Doc (doc) + Title (text) + Description
(text) columns in the schema row. `doc` column is system-managed: on row
insert, backend auto-creates an empty `.md` at MinIO key
`{workspace_id}/{table_id}/{row_number}.md` and writes the path into the
cell. Users cannot edit `doc` cell values directly.

## URL Pattern

```
/<workspace_id>/<table_id>              → table view
/<workspace_id>/<table_id>/<row_number> → row detail
```

`table_id` is the lowercase table name (string). `workspace_id` is UUID.

## Reserved Names

`__schema__` and `__order__` are reserved for meta-rows. POST/PUT views
reject those names; the BE filters them out of `GET /views` and the
view-order endpoint self-heals stale entries.
