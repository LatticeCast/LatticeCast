# Views

- A named view is `(table_id, view_id)` with `{name, type, ...}` in `config`.
  `view_order` and `default_view` are in the table schema.
- Types: `table`, `kanban`, `timeline`, `dashboard`, `workflow`. Controllers
  update stores from API responses; components render `$derived` store state.
- PM: table, Kanban, timeline over ticket rows. This avoids a PM-only data
  model. Ticket key is
  `<type>-<row_id>`; detail is a text blob.
- CRM: Kanban plus Grafana-like dashboard. Dashboard blocks use LQL over CRM
  rows, not a copied analytics dataset or CRM-only API.

```text
dashboard block -> POST /tables/{table_id}/views/{view_name}/blocks/{block_id}/query
-> membership + dashboard check -> LQL -> RLS SQL -> dashboard store -> UI
```

- Blocks are `chart`, `number`, or `list`; cache key is
  `(table_id, view_name, block_id)`. LQL is server-compiled against workspace
  schema so it keeps membership/RLS scope; invalidate schema cache after column
  changes.
- LQL `<`, `<=`, `>`, `>=` are numeric when either side is a `number`,
  `date` or `datetime` column or a numeric literal (LatticeQL 0.6.3); empty or
  non-numeric cells read as NULL. A non-numeric literal is a 400; a database
  type error from the query is a 422. `select`, `bool`, `url` kinds are
  deprecated for `text` plus a display hint (LatticeQL 0.6.4).
