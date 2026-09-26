# Frontend

SvelteKit 2 + Svelte 5. Server data has one client cache only.

```text
event -> lib/backend controller -> API -> authoritative response -> store -> $derived UI
```

- Routes compose UI, controllers own server communication and cache updates,
  stores hold shared data, and components own only transient UI state.
- Render shared data with `$derived`; use `$state` for UI-only state and
  `$effect` only for genuine external side effects.
- Never duplicate or optimistically reconstruct authoritative server data in a
  component; the controller response replaces the shared cache.
- The frontend is the only place a timezone exists. Server times are UTC+0 with no zone; convert on display and convert back on write. Never send a local-time-derived instant.
- `date`/`datetime` cells are epoch-millisecond numbers. Format them for display only; do not parse display strings back into the write path.
- Use `workspace_id` internally; a table ID can repeat across workspaces.
