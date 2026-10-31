# LatticeCast

Self-hosted Airtable-like table engine. PM/CRM/workflow are seeded schemas and views, not separate domain backends.

```text
Browser -> nginx -> SvelteKit | FastAPI -> PostgreSQL (RLS) + S3-compatible storage
```

## Rules

- Identity: `workspace_id`; table identity: `table_id` (BIGINT, DB-assigned), display name `table_name` unique per workspace; row/view IDs are per-table numbers.
- Schema is `tables.config`; `rows.row_data` is keyed by column UUID.
- Every RDS time column is `TIMESTAMPTZ` and represents a UTC instant. Only `rows.row_data` `date`/`datetime` cells are epoch-millisecond JSON numbers; localisation is the frontend's job.
- PostgreSQL RLS is the authorization boundary, and the only one. Mutating PG functions run as the caller (SECURITY INVOKER), so RLS decides; `SECURITY DEFINER` is reserved for operations that must cross it (index DDL, blob registration, sidebar, self-service identity). Route-level `_require_owner`/`_require_write` checks only read RLS-visible grants to return a friendlier error; they grant nothing. An unreadable resource answers 404, never 403. UI follows controller -> API -> response -> store -> `$derived` UI; components never duplicate authoritative cache data in local state.
- Blob cells are storage-backed metadata, mutated only by the addressed blob routes/functions.
- API: `backend/src/router/api/`; DB: `migration/V*.sql`; runtime: `docker-compose.yml`; exact contracts: models/OpenAPI.

LC is a unified backend: different front-end apps need only their own schemas and views on the same API, SSO, and storage.

## Guides

`llm.devops.md` workflow/runtime · `llm.core.md` workspace/table/row/storage invariants · `llm.sso.md` identity, membership, and RLS access · `llm.views.md` PM/CRM/table/dashboard views and LQL · `llm.storage.md` blobs · `llm.e2e.md` API/UI/snapshot verification.
