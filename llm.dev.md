# LatticeCast — Development Guide

Use this file for the normal local workflow. Architecture lives in
`llm.root.md`; specialized checks live in the linked documents and skills.

## Start the Stack

```bash
docker compose up -d db minio
docker compose --profile migration run --rm migration
docker compose up -d
curl http://localhost:13491/api/v1/status
```

The public entry point is `http://localhost:${NGX_PORT}`; the default in
`.env.example` is `13491`. Nginx sends `/api/*` to FastAPI and everything else
to the Vite frontend.

## Work by Area

| Change | Primary paths | Minimum checks |
|---|---|---|
| Frontend | `frontend/src/` | `npm run check`, `npm run build`, focused E2E/snapshot |
| Backend | `backend/src/` | `ruff check`, focused API/E2E test |
| Database | `migration/` | dump, migration test, checksum update, apply |
| E2E | `e2e/` | focused pytest, then affected package/suite |
| Deployment | `docker-compose.yml`, `k8s/` | render/config validation and service smoke test |

Run commands in the existing containers when the stack is available:

```bash
docker compose exec frontend npm run check
docker compose exec frontend npm run build
docker compose exec backend ruff check src
docker compose --profile test exec e2e pytest -v
```

Dependency changes require rebuilding the affected image. Frontend and backend
source are bind-mounted for local development.

## Database Changes

`migration/V*.sql` and `migration/checksums.txt` are the source of truth. Never
edit an applied migration; add a new ordered file.

The runner requires a database dump before migration work:

```bash
docker compose --profile migration run --rm --entrypoint python migration migrate.py --dump
docker compose --profile migration run --rm migration --test-only
docker compose --profile migration run --rm --entrypoint python migration migrate.py --hash
docker compose --profile migration run --rm migration
```

Read `.agent-skills/developing/db-sql/SKILL.md` before touching migration SQL.

## Frontend Rule

All server-backed changes follow:

```text
component -> controller -> backend -> response -> store -> $derived -> GUI
```

The response is authoritative. Do not mutate a component-only copy of server
state. See `llm.frontend.md` and
`.agent-skills/developing/svelte/SKILL.md`.

## E2E and Visual Verification

```bash
docker compose --profile test up -d browser e2e
docker compose --profile test exec e2e pytest tables/test_row_update.py -v
docker compose --profile test exec e2e pytest -v --snapshot
```

Tests target the real stack and remote Chromium. Wait for observable page state,
not fixed sleeps. Screenshots are written to `.browser/`. See `llm.e2e.md` and
`llm.snapshot.md`.

## Useful Diagnostics

```bash
docker compose ps
docker compose logs backend
docker compose logs frontend
docker compose exec db pg_isready -U dba_user -d "$POSTGRES_DB"
```

Common causes: unapplied migrations, a stale image after dependency changes,
missing user bootstrap data, or a frontend controller that did not update its
store from the backend response.
