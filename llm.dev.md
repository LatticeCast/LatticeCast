# Dev Guide

> Deploy: `llm.deploy.md` | Schema: `llm.arch.db.md` | Skills: `Skill(developing-fastapi)`, `Skill(developing-db-sql)`

## Bootstrap (from zero)

```bash
# 1. DB + migrations
docker compose up -d db
docker compose exec db pg_isready -U dba_user -d db
docker compose --profile migration run --rm migration

# 2. Seed dev user (app_user lacks INSERT on auth — must use DBA)
docker compose exec db psql -U dba_user -d db -c "
  INSERT INTO auth.users (user_id, role) VALUES (gen_random_uuid(), 'user');"
USER_ID=$(docker compose exec -T db psql -U dba_user -d db -t -A -c \
  "SELECT user_id FROM auth.users LIMIT 1")
docker compose exec db psql -U dba_user -d db -c "
  INSERT INTO gdpr.user_info (user_id, email, user_name)
  VALUES ('$USER_ID', 'lattice@latticecast.local', 'lattice');"

# 3. Start + verify
docker compose up -d
curl http://localhost:13491/api/v1/status
curl http://localhost:13491/api/v1/workspaces -H "Authorization: Bearer lattice"
```

## Auth (dev mode)

`AUTH_REQUIRED=false` in `.env`. Bearer token resolves: UUID → `user_name` → email.

## Frontend

```bash
docker compose up frontend -d       # Vite dev, HMR auto
docker compose exec frontend npm run lint && docker compose exec frontend npm run build
```

Playwright snapshot (MUST after FE changes) — see `Skill(developing-debug-frontend)`:
```bash
docker compose --profile test up -d browser
docker compose exec browser python3 browser/snapshot_page.py <path>
```

## Backend

```bash
docker compose up backend -d        # reload=True auto-picks up src/ changes
curl http://localhost:13491/api/v1/status
```

UV-based image (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), `uv pip install --system` — no `.venv`.
Host `./backend/` bind-mounted to `/app/`. Log rotation: `json-file`, 100m × 50 files.

**Deps change**: rebuild image (`docker compose build backend && docker compose restart backend`).
`lattice-ql`: bump tag in `backend/pyproject.toml`, rebuild.

**Async rule**: all I/O must be awaitable — sync calls freeze the event loop. See `Skill(developing-fastapi)`.

## Migrations

```bash
# Add V<N>__name.sql — never modify existing files
docker compose --profile migration run --rm migration --test-only
docker compose --profile migration run --rm --entrypoint python migration migrate.py --hash
docker compose --profile migration run --rm migration
git add migration/V<N>__*.sql migration/checksums.txt
```

See `Skill(developing-db-sql)` for full workflow.

## E2E Tests

pytest-based in `e2e/`. Browser in separate container (Playwright `run-server` on `:4444`),
e2e connects via WS. Both under `--profile test`, `network_mode: host`.

```bash
docker compose --profile test up -d
docker compose exec e2e pytest e2e/workspace/test_create.py -v   # single test
docker compose exec e2e pytest                                    # all tests
```

See `Skill(developing-e2e)`.

## curl Smoke Tests

```bash
curl http://localhost:13491/api/v1/status
curl http://localhost:13491/api/v1/workspaces -H "Authorization: Bearer lattice"
curl "http://localhost:13491/api/v1/tables?workspace_id=<uuid>" -H "Authorization: Bearer lattice"
curl "http://localhost:13491/api/v1/tables/<table_id>/rows?limit=50" -H "Authorization: Bearer lattice"
```

## Common Issues

| Symptom | Fix |
|---|---|
| "permission denied for table users" | Seed via DBA (see bootstrap) |
| Checksum mismatch | Don't modify applied V*.sql — add new V<N+1> |
| 502 on `/api/*` | `docker compose logs backend` |
