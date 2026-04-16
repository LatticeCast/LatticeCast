# LLM Context - Lattice Cast

## Project Overview

Self-hosted Airtable + Jira. Flexible tables with JSONB, customizable views
(Table, Kanban, Timeline), built-in PM with ticket docs in MinIO.

**Domain:** `lattice-cast.posetmage.com`

> **Documentation:**
> - `llm.dev.md` - Local dev workflow
> - `llm.frontend.md` - Frontend (Svelte 5 + Tailwind 4)
> - `llm.arch.db.md` - DB schemas, roles, migrations, RLS
> - `llm.arch.auth.md` - OAuth flow
> - `llm.endpoint.md` - API endpoints
> - `llm.storage.md` - MinIO storage (aioboto3 async)
> - `llm.user.md` - User management
> - `llm.deploy.md` - Docker / k8s deployment

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | SvelteKit 2, Svelte 5 (Runes), Tailwind 4, Vite 7, TS 5.9 |
| Backend | FastAPI, Python 3.12, SQLModel, asyncpg, **aioboto3** (native async) |
| DB | PostgreSQL 18 — JSONB, GIN/B-tree indexes, RLS policies |
| Cache | Valkey 8 (redis-compat) |
| Storage | MinIO (S3-compat) — ticket markdown docs |
| Auth | Google OAuth, Authentik (PKCE) |
| Infra | Docker Compose (dev), Kubernetes (prod) |

## Architecture

```
Browser → Nginx :13491
           ├── /api/*  → Backend (FastAPI)
           └── /*      → Frontend (Vite)

Backend → PG (asyncpg, app/login roles)
        → Valkey (JWKS + shared cache)
        → MinIO (aioboto3 — never blocks event loop)
```

## Connection Roles

| Role | Use case | Schema access |
|---|---|---|
| `dba_user` | Migrations only (DBA pwd in docker-compose, NOT .env) | ALL |
| `app_user` | General API | public CRUD + auth SELECT |
| `login_user` | Auth endpoints | auth CRUD only |

## Directory Structure

```
lattice-cast/
├── backend/                FastAPI + Python 3.12 (submodule)
│   └── src/
│       ├── main.py         app entry (lifespan = connection pool init only)
│       ├── config/         settings, database, redis, storage (aioboto3)
│       ├── core/db.py      app_engine + login_engine
│       ├── middleware/     auth (get_current_user, get_rls_session)
│       ├── models/         SQLModel definitions
│       ├── repository/     CRUD layer
│       └── router/api/     FastAPI routers
├── frontend/               SvelteKit + Tailwind (submodule)
│   └── src/
│       ├── routes/         +page.svelte per route
│       └── lib/            stores, components, API clients
├── migration/              V*.sql + migrate.py runner
│   ├── .sqlfluff           strict lint (80 char, align CREATE TABLE)
│   ├── checksums.txt       committed SHA-256 integrity
│   └── migrate.py          lint → verify → test → apply pipeline
├── k8s/                    production manifests
├── nginx/                  reverse proxy config
├── browser/                Playwright automation
└── docker-compose.yml      DBA creds hardcoded here (not .env)
```

## Database Schema (current, after V30)

See `llm.arch.db.md` for full details.

```
auth.users         (user_id UUID PK, role, created_at, updated_at)
auth.user_info     (user_id UUID FK, user_name UNIQUE, email, name)
public.workspaces  (workspace_id UUID PK, workspace_name UNIQUE)
public.workspace_members  ((workspace_id, user_id) PK, role)
public.tables      ((workspace_id, table_id) composite PK, columns JSONB, views JSONB)
public.rows        ((workspace_id, table_id, row_number) composite PK, row_data JSONB)
private.schema_migrations  (filename, checksum SHA-256, applied_at)
```

Notes:
- Column defs + view configs in `tables.columns` / `tables.views` JSONB
- Auto-managed PG indexes per column: B-tree (num/date), GIN (select/tags/text)
- Ticket docs: MinIO at `{workspace_id}/{table_id}/{row_number}.md`
- RLS on `tables` + `rows` enforces workspace membership

## Key Patterns

### Backend
- **Async-native I/O everywhere** — sync DB/S3/HTTP call freezes event loop for ALL users. See `Skill(developing-fastapi)`.
- **aioboto3 for S3** — `async with s3_client() as s3: await s3.put_object(...)`
- **RLS session** — `get_rls_session` sets `app.current_user_id`; PG policies enforce workspace isolation
- **Repository pattern** — all DB ops in `repository/` layer
- **OpenAPI** — auto-generated at `/api/v1/docs`

### Migrations
- **Flyway format** — `V<N>__name.sql`, tracked in `private.schema_migrations`
- **Never modify applied file** — checksum mismatch aborts
- **Add new V<N+1>.sql** → `python migrate.py --hash` → commit both
- See `Skill(developing-db-sql)` for workflow

### Frontend
See `llm.frontend.md` for Svelte 5 + Tailwind 4 patterns.

## API Prefix

All routes live under `/api/v1/*`:

| Route | Purpose |
|---|---|
| `/api/v1/status` | Health check |
| `/api/v1/auth/*` | OAuth endpoints |
| `/api/v1/workspaces/*` | Workspace + members CRUD |
| `/api/v1/tables/*` | Tables + columns + views |
| `/api/v1/tables/{id}/rows/*` | Row CRUD + doc endpoints |
| `/api/v1/storage/*` | User file upload/download |
| `/api/v1/admin/*` | Admin-only endpoints |

## Dev Bootstrap

```bash
docker compose up -d db
docker compose --profile migration run --rm migration    # lint→test→apply
docker compose up -d                                     # full stack
```

Default dev user `lattice` must be seeded via DBA (auto-create currently
fails due to app_user lacking INSERT on auth). See `llm.dev.md`.
