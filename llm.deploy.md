# LatticeCast — Deployment and Runtime

`docker-compose.yml` is the local runtime source of truth. `k8s/` contains the
production manifests. Environment names and safe examples live in
`.env.example`.

## Compose Topology

```text
host :${NGX_PORT} -> lattice-cast (nginx)
                         |-- frontend (Vite)
                         `-- backend (FastAPI)
                                |-- db (PostgreSQL)
                                `-- minio (S3-compatible storage)
```

| Service | Role | Persistent/source mount |
|---|---|---|
| `lattice-cast` | Public reverse proxy | nginx template |
| `frontend` | SvelteKit dev server | `./frontend` bind mount |
| `backend` | FastAPI workers | `./backend` bind mount |
| `db` | PostgreSQL data and PG cache | `db_data` volume |
| `minio` | Documents and generic files | `.minio_data/` |
| `migration` | SQL migration runner | `./migration`, migration profile |
| `browser` | Remote Chromium server | `.browser/`, test profile |
| `e2e` | pytest/Playwright client | `./e2e`, `.browser/`, test profile |

The backend reaches database/MinIO through `app-network`. Nginx, frontend, and
backend share the external `shared-network`. The E2E and browser services use
host networking so Chromium reaches the same public URL as a developer.

## Common Commands

```bash
docker compose up -d
docker compose ps
docker compose logs backend
docker compose --profile migration run --rm migration
docker compose --profile test up -d browser e2e
docker compose build frontend backend
```

Use `llm.dev.md` for the required migration dump/test/hash sequence; the short
command above is only normal startup/application of already-reviewed files.

## Configuration Groups

| Group | Examples |
|---|---|
| Public entry point | `NGX_PORT` |
| PostgreSQL | `POSTGRES_DB`, app/manager passwords |
| Local JWT | secret key and expiry |
| OAuth | Google and Authentik client settings |
| MinIO | endpoint, access key, secret, bucket |
| E2E target | base URL and browser WebSocket override |

Frontend provider values are supplied as build arguments and baked by Vite.
Backend/runtime secrets remain environment variables. Do not copy real `.env`
values into documentation, manifests, logs, or commits.

## Kubernetes

The `k8s/` directory separates namespace/config, deployments, services, and
ingress resources for frontend, backend, database, and MinIO. Read
`k8s/README.md` before applying them. TLS secrets and image publication are
external deployment steps, not encoded in the onboarding docs.

## Gotchas

- `shared-network` is external and must exist for Compose startup.
- Source changes hot-reload, but dependency or Dockerfile changes require an
  image rebuild.
- Database and MinIO data outlive containers through their mounts.
- Test screenshots are shared through `.browser/`; do not use `docker cp`.
- Validate the rendered Compose/Kubernetes configuration before deployment.
