# Dashboard View

Dashboard is a table view whose blocks run LatticeQL against the same rows as other views.

```text
block config -> dashboard controller -> dashboard query endpoint -> LatticeQL -> RLS SQL
-> authoritative rows -> dashboard block cache -> $derived chart/number/list UI
```

- View config stores grid layout and discriminated blocks (`chart`, `number`, `list`).
- Block endpoint addresses a view by name and block ID.
- `lib/backend/dashboard.ts` owns block requests and writes the response into
  `dashboard.store.ts`, keyed by `(table_id, view_name, block_id)`. Dashboard
  blocks only derive that cache entry; they do not fetch or copy query rows.
- Ignore an older request result when a newer request for the same cache key is
  in flight, so a stale response cannot overwrite the authoritative one.
- Invalidate the LatticeQL schema cache after column changes.
- Extend a block kind across model, frontend type, renderer, and dispatcher.
