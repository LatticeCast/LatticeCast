# Dashboard View

Dashboard is a table view whose blocks run LatticeQL against the same rows as other views.

```text
block config -> dashboard query endpoint -> LatticeQL -> RLS SQL -> rows -> chart/number/list
```

- View config stores grid layout and discriminated blocks (`chart`, `number`, `list`).
- Block endpoint addresses a view by name and block ID.
- Invalidate the LatticeQL schema cache after column changes.
- Extend a block kind across model, frontend type, renderer, and dispatcher.
