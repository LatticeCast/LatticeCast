# LLM Context — Lattice Cast

Self-hosted Airtable + Jira/CRM. JSONB tables, views (Table/Kanban/Timeline/Workflow/Dashboard), PM/CRM templates, ticket docs in MinIO.
- **Layer-1** — generic JSONB table engine with sort/filter/group, auto indexes, RLS.
- **Layer-2** — template seeders only: `POST /api/v1/tables/template/{kind}` (pm/crm/workflow).

**Docs:** `llm.dev.md` `llm.frontend.md` `llm.arch.{airtable,pm,dashboard,db,auth}.md` `llm.endpoint.md` `llm.storage.md` `llm.e2e.md` `llm.snapshot.md` `llm.user.md` `llm.deploy.md`

## Tech Stack

| Layer | Tech |
|-------|------|
| FE | SvelteKit 2, Svelte 5 Runes, Tailwind 4, Vite 7, TS 5.9, ECharts 5 |
| BE | FastAPI, Python 3.12, SQLModel, asyncpg, aioboto3 (async S3) |
| DB | PostgreSQL 18 — JSONB, GIN/B-tree, RLS | Cache: Valkey 8 |
| Storage | MinIO (ticket markdown docs) | Auth: Google OAuth, Authentik PKCE |
| Infra | Docker Compose (dev, UV-based images), Kubernetes (prod) |
| DSL | `lattice-ql` — compiles dashboard block queries to PG SQL |

## Architecture

```
Browser → Nginx :13491 → /api/* FastAPI | /* Vite
BE → PG (app_engine + login_engine) → Valkey (JWKS cache) → MinIO (aioboto3)
```

**Roles:** `dba_user` (migrations, ALL) · `app_user` (CRUD + RLS) · `mgr_user` (BYPASSRLS, login/admin)

## Directory

```
backend/src/
  main.py              lifespan: pool + valkey + JWKS + MinIO
  config/              settings, redis, storage, lattice_ql
  core/db.py           app_engine + login_engine
  middleware/           auth, jwks, token
  models/ repository/  SQLModel + CRUD layer
  router/api/
    tables/            crud, columns, views, templates, _shared
    table_schemas.py   GET /sidebar
    rows, dashboard, storage, auth, workspaces, admin/users
frontend/src/
  routes/              +layout.ts (auth gate), [workspace_id]/[table_id]/
  lib/backend/         http, tables, views, table_schemas, workspaces, storage
  lib/stores/          table_schema, table_schemas, table_rows, table_views, table_workflow, tables, auth, settings
  lib/components/      sidebar/, layout/ (TopBar), table/ (cells/), workflow/, dashboard/
  lib/charts/          EChart.svelte (ECharts 5)
migration/             V1..V30 SQL + migrate.py (lint→verify→test→apply)
e2e/                   Playwright + pytest
```

## DB Schema

4 schemas: `public`, `auth`, `gdpr`, `private` (migrations only). See `llm.arch.db.md`.

```
auth.users · gdpr.user_info · public.workspaces · public.workspace_members
public.tables       (config={columns, view_order, default_view})
public.table_views  (config={name, type, ...}, view_id BIGINT auto-inc)
public.rows         (row_data JSONB, row_id BIGINT)
private.schema_migrations
```

- V23 merged table_schemas → tables.config · V26 CHECK on view type · V29 default_view=0 · V30 ON UPDATE CASCADE on FKs
- PG functions own schema/view mutations — BE repos are thin wrappers. RLS on all public + gdpr tables.

## Key Patterns

- **Async-native I/O** — sync calls freeze the event loop. See `Skill(developing-fastapi)`.
- **RLS session** — `get_rls_session` → `app.current_user_id` → PG policies enforce isolation
- **Migrations** — V1–V14 squashed baseline (v0.40), head **V30**. Flyway format, checksum-tracked. See `Skill(developing-db-sql)`.
- **FE stores** split by concern; layout = Sidebar + TopBar; cells in `table/cells/`

## API Routes (`/api/v1/*`)

| Route | Purpose |
|---|---|
| `/status` `/settings` | Health, config |
| `/login/*` | OAuth token exchange |
| `/workspaces/*` | Workspace + members CRUD |
| `/sidebar` | Sidebar table-schema tree |
| `/tables/*` | Tables CRUD, columns, views |
| `/tables/template/{kind}` | Seeders: pm, crm, workflow |
| `/tables/{tid}` PATCH | Schema patches |
| `/tables/{id}/rows/*` | Row CRUD + docs |
| `/tables/{id}/views/{vid}/blocks/{bid}/query` | Dashboard LatticeQL |
| `/storage/*` | File upload/download |
| `/admin/*` | Admin endpoints |

## Dev Bootstrap

```bash
docker compose up -d db && docker compose --profile migration run --rm migration && docker compose up -d
```

Dev user `lattice` seeded via DBA. See `llm.dev.md`.
