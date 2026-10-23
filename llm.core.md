# Core

```text
workspace UUID -> table BIGINT -> row/view/blob children
```

- `workspace_id` is the membership boundary. `table_id` is global BIGINT;
  `table_name` is unique only within one workspace, so names cannot be used in
  table routes after v0.80.
- Rows: `(table_id, row_id)`, JSONB `{column_id: value}`. Views:
  `(table_id, view_id)`, config JSONB. IDs are per-table, monotonic BIGINT.
- Schema holds ordered columns, `view_order`, and `default_view`; view `0` is
  the implicit Schema view.
- V71 removed child `workspace_id`: duplicating it allowed a child to claim a
  workspace different from its parent table. Children now derive RLS scope from
  the table FK.
- PATCH merges non-blob cells; PUT replaces non-blob cells. Blob writes use
  `/tables/{table_id}/rows/{row_id}/blob/{column_id}` only.
- `date`/`datetime` row values are UTC epoch milliseconds; DB timestamps are
  UTC `TIMESTAMPTZ`.
- RLS is the authorization boundary; normal routes use its session, login/admin
  use the manager session. PG functions own schema/view/order and row writes so
  API and direct writes preserve invariants. Never edit an applied migration.
