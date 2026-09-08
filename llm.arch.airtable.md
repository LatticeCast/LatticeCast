# Generic Table Engine

All templates use the same tables, views, and rows.

```text
tables.config: columns + view_order + default_view
table_views.config: named view configuration
rows.row_data: { column_uuid: value }
```

- A table is `(workspace_id, table_id)`; row/view IDs are numeric per-table. `row_id` is allocated from an atomic counter, monotonic and never reused.
- Column position comes from schema ordering, never from row data.
- `date` and `datetime` cells share one storage shape: a JSON number of epoch milliseconds, UTC+0. `date` lands on UTC midnight. The column type only says how to render and edit it; granularity is never inferred from the value. Empty is `null`, never `0`.
- PG functions own schema/view/order mutations; their returned schema snapshot replaces frontend cache.
- View `0` is the implicit table view. Exact shapes/enums belong in models and migrations.
- Blob values are metadata, not ordinary row values; use blob endpoints/functions.
