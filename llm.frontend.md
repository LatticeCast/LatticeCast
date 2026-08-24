# Frontend

SvelteKit 2 + Svelte 5. Server data has one client cache only.

```text
event -> lib/backend controller -> API -> authoritative response -> store -> $derived UI
```

- Routes compose UI; `lib/backend/` owns server calls/store updates; `lib/stores/` owns cached data; components own only transient UI state.
- Main table caches: `table_schemas.store.ts`, `table_rows.store.ts`; schema mutations apply the returned full schema snapshot.
- Table views render the same schema/rows. Do not locally reconstruct server state after a mutation.
- Use `workspace_id` internally; a table ID can repeat across workspaces.
