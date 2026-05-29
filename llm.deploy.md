# LLM Context - Deployment

> For general project context, see `llm.md`.

## Quick Start

```bash
docker compose up                                     # all services (nginx + fe + be + db + valkey + minio)
docker compose --profile migration run --rm migration  # run DB migrations
docker compose --profile test up -d e2e browser        # e2e + headless Chromium
```

Single entry point: `http://localhost:${NGX_PORT}` (default **13491**). Nginx (`lattice-cast` service) proxies `/api/*` → backend, `/*` → frontend.

## Architecture

```
browser → :13491 nginx (lattice-cast)
              ├─ /api/*  → backend:13491  (uvicorn × 4 via supervisord)
              └─ /*      → frontend:13491 (vite dev server)
         backend → db:5432, valkey:6379, minio:9000
```

## Services (docker-compose.yml)

| Service | Image / Build | Network | Notes |
|---------|---------------|---------|-------|
| `lattice-cast` | nginx:alpine | shared-network | Reverse proxy, single exposed port `NGX_PORT` |
| `frontend` | `./frontend` (node:24) | shared-network | Vite dev server, source-mounted |
| `backend` | `./backend` (uv/python3.12-bookworm-slim) | shared + app | Supervisord → uvicorn --workers 4 |
| `db` | postgres:18 | app-network | Port 15432 exposed to host |
| `valkey` | valkey/valkey:8-alpine | app-network | appendonly, 256mb maxmemory |
| `minio` | minio/minio:latest | app-network | Console on :9001 (internal) |

### Profiles

| Profile | Services | Purpose |
|---------|----------|---------|
| `migration` | `migration` | DB migrations (Python migrate.py, mounts docker.sock) |
| `test` | `e2e`, `browser` | E2E: uv + Playwright client; Browser: Chromium run-server :4444. Both use `network_mode: host` |

### Networks

- `app-network` (bridge) — internal: backend, db, valkey, minio, migration
- `shared-network` (external) — nginx ↔ frontend ↔ backend; cross-compose communication

### Volumes / Mounts

| Mount | Type | Target |
|-------|------|--------|
| `db_data` | named volume | PostgreSQL data |
| `valkey_data` | named volume | Valkey AOF persistence |
| `.minio_data/` | bind mount | MinIO object storage |
| `./frontend` | bind mount | FE source (hot reload) |
| `./backend/` | bind mount | BE source (hot reload) |
| `.browser/` | bind mount | E2E screenshot output |

## Dockerfiles

| Path | Base | Purpose |
|------|------|---------|
| `frontend/Dockerfile` | node:24 | Dev + build; `npm run preview` in prod |
| `frontend/Dockerfile.build` | node:24 → scratch | Multi-stage export of `build/` dir only |
| `backend/Dockerfile` | uv:python3.12-bookworm-slim | Supervisord entry; installs from pyproject.toml |
| `migration/Dockerfile` | uv:python3.12-bookworm-slim | Docker CLI + psycopg2 + sqlfluff |
| `e2e/Dockerfile` | uv:python3.12-bookworm-slim | Playwright client (no browsers) |
| `browser/Dockerfile` | playwright/python:v1.50.0-noble | Chromium host, run-server :4444; mem_limit 2g |

## Kubernetes (Production)

```
k8s/
├── namespace/lattice-cast.yaml
├── configmaps/backend-config.yaml
├── {frontend,backend,db,valkey,minio}-deployment.yaml
├── {frontend,backend,db,valkey,minio}-service.yaml
└── {frontend,backend}-ingress.yaml
```

```bash
kubectl apply -f k8s/namespace/
kubectl apply -f k8s/configmaps/
kubectl create secret tls lattice-cast-tls-secret --key domain.key --cert domain.pem -n lattice-cast
kubectl apply -f k8s/
```

### Build & Push

```bash
set -a && source .env && set +a && docker compose build
docker tag lattice-cast-frontend:latest 127.0.0.1:7000/lattice-cast-frontend:latest
docker tag lattice-cast-backend:latest  127.0.0.1:7000/lattice-cast-backend:latest
docker push 127.0.0.1:7000/lattice-cast-frontend:latest
docker push 127.0.0.1:7000/lattice-cast-backend:latest
```

Frontend build requires `GOOGLE_CLIENT_ID`, `AUTHENTIK_URL`, `AUTHENTIK_CLIENT_ID` exported — Vite bakes them at build time via docker-compose build args.

### Ingress

| Path | Service |
|------|---------|
| `/` | frontend-service |
| `/api/*` | backend-service |

## Environment Variables (.env.example)

| Variable | Description |
|----------|-------------|
| `NGX_PORT` | Single exposed port (default 13491) |
| `POSTGRES_DB` | Database name |
| `POSTGRES_APP_PASSWORD` | app_user (RLS-enforced CRUD) |
| `POSTGRES_MGR_PASSWORD` | mgr_user (BYPASSRLS, login/admin) |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth (build-time for FE) |
| `AUTHENTIK_URL/CLIENT_ID` | Authentik OAuth (build-time for FE) |
| `MINIO_*` | MinIO S3 storage (root user, endpoint, bucket) |
| `SAMPLE_USER/PASSWORD` | Dev seed user |
| `E2E_BASE_URL` | Override e2e target (default: local stack) |

DB DBA creds (`dba_user`/`dba_pws`) are hardcoded in `docker-compose.yml`, not in `.env`.
