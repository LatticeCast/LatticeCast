# Airtable Core (Layer 1)

The generic table engine. Everything here works for ANY table — PM, CRM, or custom.

## Schema

See `migration/test_migration_schema.py` for exact columns. Key points:

- `public.tables` — identity + `config JSONB` holding `{columns, view_order, default_view}`
- `public.table_views` — one row per view, PK `(workspace_id, table_id, view_id BIGINT)`
- `public.rows` — `row_data JSONB`, per-column auto-indexes

All schema mutations go through PG functions — see `migration/V13__schema_functions.sql` (rewritten in V23).

## Column Types

See `_build_column_dict()` in `migration/V12__template_functions.sql` and
index creation in `migration/V11__index_helper.sql`.

Types: `text`, `number`, `date`, `datetime`, `select`, `tags`, `checkbox`, `url`, `email`, `phone`, `doc`.

## Views

View types: `table`, `kanban`, `timeline`, `dashboard`.
View CRUD functions: `migration/V14__view_functions.sql` (rewritten in V23).

The implicit "Schema" view (view_id=0) is FE-only — no DB row.

## Option Colors

All hex from BE. Stored in column options: `{"choices": [{"value": "todo", "color": "#9ca3af"}, ...]}`.
FE renders via `colorToStyle(hex)` — no local color palettes.

## Templates

See `_seed_blank`, `_seed_pm`, `_seed_crm` in `migration/V12__template_functions.sql`.
Dispatcher: `create_table_from_template(ws, tid, kind, by)`.
