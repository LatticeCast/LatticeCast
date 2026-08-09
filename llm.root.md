# LatticeCast — Repository Map

LatticeCast is a self-hosted Airtable-like table engine. PM, CRM, workflow,
and dashboard features are conventions and templates on top of the same table,
view, and row primitives.

## Read Next

| Area | Document |
|---|---|
| Local development and checks | `llm.dev.md` |
| Frontend architecture | `llm.frontend.md` |
| Database and authorization | `llm.arch.db.md`, `llm.arch.auth.md` |
| Table engine and PM layer | `llm.arch.airtable.md`, `llm.arch.pm.md` |
| Dashboard queries | `llm.arch.dashboard.md` |
| API route map | `llm.endpoint.md` |
| MinIO and ticket documents | `llm.storage.md` |
| E2E and screenshots | `llm.e2e.md`, `llm.snapshot.md` |
| Users and workspace access | `llm.user.md` |
| Compose and Kubernetes | `llm.deploy.md` |

## Runtime Architecture

```text
Browser -> nginx :${NGX_PORT}
             |-- /*       -> SvelteKit/Vite frontend
             `-- /api/*   -> FastAPI
                               |-- PostgreSQL (data, RLS, cache)
                               `-- MinIO (documents and files)
```

Stack: SvelteKit 2/Svelte 5/TypeScript/Tailwind 4, FastAPI/Python 3.12,
PostgreSQL 18, MinIO, ECharts, and `lattice-ql`.

## Repository Layout

| Path | Responsibility |
|---|---|
| `frontend/src/routes/` | SvelteKit pages and route loading |
| `frontend/src/lib/backend/` | API controllers; update stores from responses |
| `frontend/src/lib/stores/` | Client cache and derived state |
| `frontend/src/lib/components/` | Table, sidebar, workflow, and dashboard views |
| `backend/src/router/api/` | FastAPI route handlers |
| `backend/src/repository/` | Database access and PG-function wrappers |
| `backend/src/middleware/` | Token verification, user resolution, RLS sessions |
| `backend/src/config/` | Settings, MinIO, PG cache, LatticeQL adapter |
| `migration/` | Ordered SQL migrations, checksums, and schema/RLS tests |
| `e2e/` | pytest + remote Playwright tests against the live stack |
| `docker-compose.yml` | Development services and test/migration profiles |
| `k8s/` | Production manifests |

## Core Data Flow

```text
UI event -> frontend controller -> FastAPI -> repository/PG function
         <- exact API response  <- PostgreSQL/MinIO
controller updates store -> Svelte $derived state -> GUI rerenders
```

Server-backed data must follow this flow. Components do not invent a second
copy of backend state or manually patch the GUI after a successful mutation.

## Stable Invariants

- `workspace_id` is the workspace UUID identity; `workspace_name` is a display
  and browser-path alias.
- A table is keyed by `(workspace_id, table_id)`; rows and views add their
  per-table numeric IDs.
- Table columns and ordering live in `public.tables.config`; row values live in
  `public.rows.row_data`, keyed by column UUID.
- Workspace access is materialized as `read`, `write`, and `owner` action rows.
  PostgreSQL RLS is the final authorization boundary.
- Schema/view mutations return a full schema snapshot so the frontend can
  replace its cache from the server response.
- Ticket document keys begin with the workspace UUID, never a user name or
  workspace display name.
- `workspace_name` and `table_id` are path-facing and cannot contain `.`.
- Backend I/O is async. Do not add blocking database, HTTP, or S3 calls to the
  event loop.

## Source of Truth

- API: FastAPI decorators under `backend/src/router/api/` and generated OpenAPI.
- Database: `migration/V*.sql`; assertions live in
  `migration/test_migration_schema.py` and `migration/test_migration_rls.py`.
- Frontend state flow: controllers in `frontend/src/lib/backend/`, then stores
  in `frontend/src/lib/stores/`, then `$derived` UI.
- Runtime topology and environment wiring: `docker-compose.yml` and
  `.env.example`.
