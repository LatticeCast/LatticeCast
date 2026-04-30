# Dev Guide

> Deployment: see `llm.deploy.md`. Schema + roles: see `llm.arch.db.md`.

## Philosophy

- **Frontend**: Svelte 5 + Tailwind 4, pure CSR (no SSR)
- **Backend**: FastAPI async everywhere (`Skill(developing-fastapi)`)
- **Migrations**: `Skill(developing-db-sql)` — Flyway-style V*.sql + SQLFluff lint + checksums

## Dev Bootstrap (from zero)

```bash
# 1. DB + run migrations (lint → checksum verify → temp-DB test → apply)
docker compose up -d db
docker compose exec db pg_isready -U dba_user -d db
docker compose --profile migration run --rm migration

# 2. Seed default dev user (auto-create via API fails: app_user lacks INSERT on auth)
docker compose exec db psql -U dba_user -d db -c "
  INSERT INTO auth.users (user_id, role) VALUES (gen_random_uuid(), 'user');"
USER_ID=$(docker compose exec -T db psql -U dba_user -d db -t -A -c \
  "SELECT user_id FROM auth.users LIMIT 1")
docker compose exec db psql -U dba_user -d db -c "
  INSERT INTO auth.user_info (user_id, user_name, email, name)
  VALUES ('$USER_ID', 'lattice', 'lattice@latticecast.local', 'Lattice');"

# 3. Start full stack
docker compose up -d

# 4. Verify
curl http://localhost:13491/api/v1/status     # → {"status":"ok",...}
curl http://localhost:13491/api/v1/workspaces -H "Authorization: Bearer lattice"

# 5. Create a workspace
curl -X POST http://localhost:13491/api/v1/workspaces \
  -H "Authorization: Bearer lattice" \
  -H "Content-Type: application/json" \
  -d '{"workspace_name": "lattice-cast"}'
```

## Auth (dev mode)

`.env` sets `AUTH_REQUIRED=false`. Bearer token accepts any identifier
resolved in order: UUID → `user_name` → email.

```bash
curl -H "Authorization: Bearer lattice" ...
curl -H "Authorization: Bearer <uuid>" ...
curl -H "Authorization: Bearer user@example.com" ...
```

## Frontend Workflow

```bash
docker compose up frontend -d       # Vite dev, HMR auto
# edit src/
docker compose exec frontend npm run lint
docker compose exec frontend npm run build
```

### Playwright Snapshot (MUST after any FE change)

```bash
docker compose --profile browser up -d browser
docker compose exec browser python3 browser/snapshot_page.py <path>
ls .browser/*.png
```

See `Skill(developing-debug-frontend)` + `Skill(developing-svelte)`.

## Backend Workflow

```bash
docker compose up backend -d
# edit src/ — reload=True in uvicorn picks it up
docker compose restart backend    # if it got stuck
curl http://localhost:13491/api/v1/status
```

### Deps change

Backend mounts `./backend/:/app/` which overwrites the image's `.venv`
(an anonymous volume at `/app/.venv` keeps the venv from being clobbered).
After `pyproject.toml` changes:

```bash
docker compose run --rm --no-deps backend uv sync --no-dev
docker compose restart backend
```

If you also changed the **Dockerfile** (e.g. added a system package to
support a new dep — `lattice-ql` needs `git` for git installs):

```bash
docker compose build backend
docker compose run --rm --no-deps backend uv sync --no-dev    # refresh .venv anon volume
docker compose restart backend
```

`backend/uv.lock` is gitignored — uv re-resolves it on every image build,
no need to commit or sync it back to the host.

`lattice-ql` is pulled from `git+https://github.com/latticeCast/LatticeQL@<tag>`
(see `backend/pyproject.toml`). To bump it, change the tag and re-run the
sequence above.

### Async Rule (critical)

All I/O must be awaitable. A sync call (boto3, requests, time.sleep)
freezes the event loop → all users stall. See `Skill(developing-fastapi)`.

## Migration Workflow

```bash
# Add V<N>__name.sql — never modify existing files
cp migration/V30__rls_handle_empty_uuid.sql migration/V31__my_change.sql
# ... edit

# Verify + apply
docker compose --profile migration run --rm migration --test-only
docker compose --profile migration run --rm --entrypoint python migration \
  migrate.py --hash
docker compose --profile migration run --rm migration

# Commit BOTH the V*.sql AND checksums.txt
git add migration/V31__my_change.sql migration/checksums.txt
```

See `Skill(developing-db-sql)` for full editing workflow + rules.

## curl Smoke Tests

```bash
# Health
curl http://localhost:13491/api/v1/status

# Workspaces
curl http://localhost:13491/api/v1/workspaces -H "Authorization: Bearer lattice"

# Tables (in workspace)
curl "http://localhost:13491/api/v1/tables?workspace_id=<uuid>" \
  -H "Authorization: Bearer lattice"

# Rows (in table)
curl "http://localhost:13491/api/v1/tables/<table_id>/rows?limit=50" \
  -H "Authorization: Bearer lattice"

# Admin
curl http://localhost:13491/api/v1/admin/users \
  -H "Authorization: Bearer lattice"
```

## Common Issues

| Symptom | Fix |
|---|---|
| "permission denied for table users" | app_user lacks INSERT on auth. Seed user via DBA (see bootstrap) |
| Checksum mismatch on migration | File edited after apply. Add a new V<N+1>, don't modify. |
| 502 on `/api/*` | Backend not ready. `docker compose logs backend` |
| Frontend not updating | `docker compose restart frontend` |
| `.venv/bin/python: No such file` | Volume mount overwrote built venv. Run `uv sync` (see above) |

## K8s Deploy

Only on explicit request. See `llm.deploy.md`.
