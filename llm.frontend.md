# Frontend

SvelteKit 2 + Svelte 5. Server data has one client cache only.

```text
event -> lib/backend controller -> API -> authoritative response -> store -> $derived UI
```

- Routes compose UI; `lib/backend/` owns server calls/store updates; `lib/stores/` owns cached data; components own only transient UI state.
- Main table caches: `table_schemas.store.ts`, `table_rows.store.ts`; schema mutations apply the returned full schema snapshot.
- Table views render the same schema/rows. Do not locally reconstruct server state after a mutation.
- The frontend is the only place a timezone exists. Server times are UTC+0 with no zone; convert on display and convert back on write. Never send a local-time-derived instant.
- `date`/`datetime` cells are epoch-millisecond numbers. Format them for display only; do not parse display strings back into the write path.
- Use `workspace_id` internally; a table ID can repeat across workspaces.
