# Airtable Core (Layer 1)

The generic table engine. Everything here works for ANY table — PM, CRM, or custom.

## Tables (DDL)

Three PG tables. See `migration/test_migration_schema.py` for exact columns.

| Table | PK | Key columns |
|---|---|---|
| `public.tables` | `(workspace_id UUID, table_id VARCHAR)` | `config JSONB`, `created_by`, `updated_by` |
| `public.table_views` | `(workspace_id, table_id, view_id BIGINT)` | `config JSONB`, `created_by`, `updated_by` |
| `public.rows` | `(workspace_id, table_id, row_id BIGINT)` | `row_data JSONB`, `created_by`, `updated_by` |

- `tables.config` shape: `{columns: [{column_id, name, type, options}, ...], view_order: [view_id, ...], default_view: view_id | null}`
- `table_schemas` was merged into `tables` in `V23__merge_table_schemas_into_tables.sql`
- `row_id` and `view_id` are per-(workspace_id, table_id) auto-increment BIGINTs (BEFORE INSERT triggers in V7, V9)
- Column position = array index in `config.columns`; reorder via `update_col_order()`
- FK cascade: deleting a table cascades to `table_views` and `rows`

## PG Functions

All schema mutations go through PG functions (originally V13/V14, rewritten in V23 to target `public.tables`).

| Function | Signature | Returns |
|---|---|---|
| `add_column` | `(ws, tid, name, type, options, by)` | `config` |
| `update_column` | `(ws, tid, column_id, patch, by)` | `config` |
| `delete_column` | `(ws, tid, column_id, by)` | `config` |
| `update_col_order` | `(ws, tid, order_jsonb_array, by)` | `config` |
| `update_view_order` | `(ws, tid, order_jsonb_array, by)` | `config` |
| `update_default_view` | `(ws, tid, view_id_or_null, by)` | `config` |
| `create_view` | `(ws, tid, config, by)` | `config` |
| `update_view` | `(ws, tid, view_id, patch, by)` | `config` |
| `delete_view` | `(ws, tid, view_id, by)` | `config` |
| `create_table_from_template` | `(ws, tid, kind, by)` | `void` |

All return the full `tables.config` (except `create_table_from_template`). BE hands it straight to FE.

Column helper: `_build_column_dict(name, type, options)` in `V12__template_functions.sql`.
Index helper: `create_row_data_index / drop_row_data_index` in `V11__index_helper.sql`.

## Column Types

`text`, `number`, `date`, `datetime`, `select`, `tags`, `checkbox`, `url`, `email`, `phone`, `doc`.

## View Types

Enforced by CHECK constraint (`V26__view_type_check.sql`):
`table`, `kanban`, `timeline`, `dashboard`, `workflow`.

- Implicit "Schema" view (view_id=0) — FE-only, no DB row
- `view_id` BIGINT auto-assigned per table (BEFORE INSERT trigger, V9)
- View name/type live inside `table_views.config` JSONB: `{"name": "...", "type": "kanban", ...}`

## Option Colors

Stored in column options: `{"choices": [{"value": "todo", "color": "#9ca3af"}, ...]}`.
FE renders via `colorToStyle(hex)` — no local color palettes.

## Templates

`_seed_blank`, `_seed_pm`, `_seed_crm` in `V12__template_functions.sql`.
Dispatcher: `create_table_from_template(ws, tid, kind, by)` (rewritten in V23 to UPDATE `public.tables`).

## BE Router

`backend/src/router/api/tables/` — thin wrappers around PG functions:

| File | Routes |
|---|---|
| `crud.py` | `POST/GET/PUT/DELETE /tables`, `PATCH /tables/{tid}` (view_order, default_view, col_order) |
| `columns.py` | `POST/PATCH/DELETE /tables/{tid}/columns` |
| `views.py` | `GET/POST/PUT/DELETE /tables/{tid}/views` |
| `templates.py` | `POST /tables/template/{kind}` |

Models: `backend/src/models/table.py`, `backend/src/models/table_view.py`.

## URL Pattern

`/<workspace_id>/<table_id>/<row_id>` — all IDs, no names in URLs.
