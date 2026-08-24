# LatticeCast

Self-hosted Airtable-like table engine. PM/CRM/workflow are seeded schemas and views, not separate domain backends.

```text
Browser -> nginx -> SvelteKit | FastAPI -> PostgreSQL (RLS) + S3-compatible storage
```

## Rules

- Identity: `workspace_id`; table identity: `(workspace_id, table_id)`; row/view IDs are per-table numbers.
- Schema is `tables.config`; `rows.row_data` is keyed by column UUID.
- PostgreSQL RLS is the authorization boundary. UI follows controller -> API -> response -> store -> `$derived` UI.
- Blob cells are storage-backed metadata, mutated only by the addressed blob routes/functions.
- API: `backend/src/router/api/`; DB: `migration/V*.sql`; runtime: `docker-compose.yml`; exact contracts: models/OpenAPI.

## Guides

`llm.dev.md` workflow · `llm.frontend.md` UI state · `llm.arch.db.md` DB/RLS · `llm.arch.airtable.md` tables · `llm.storage.md` blobs · `llm.endpoint.md` API · `llm.e2e.md` tests · `llm.deploy.md` runtime.
