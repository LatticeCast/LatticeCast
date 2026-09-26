# Development

```bash
docker compose up -d db minio
docker compose --profile migration run --rm migration
docker compose up -d
docker compose exec frontend npm run check
docker compose exec frontend npm run build
docker compose exec backend ruff check src
```

- Frontend changes: type-check/build and focused E2E/snapshot. Keep server data
  in writable stores populated by controllers; review every `$effect` as a
  genuine external side effect rather than a derived-state synchronizer.
- Backend changes: Ruff and focused API/E2E test.
- DB: never alter an applied migration. Before a migration: `--dump`, `--test-only`, `--hash`, then apply via `migration/migrate.py`.
- Tests use the live Compose stack; wait on observable state, never sleeps.
- Rebuild after dependency/Dockerfile changes. Source changes hot-reload locally.

# Deployment

`docker-compose.yml` is the local runtime source; `k8s/` contains cluster manifests.

```text
nginx -> frontend + backend -> PostgreSQL + S3-compatible storage
```

- `.env.example` documents settings; never commit or log real values.
- Backend storage configuration must match an IAM/bucket policy granting bucket listing plus object read/write/delete for its configured bucket.
- Run migrations through the migration service before deploying code that depends on them.
- Source mounts hot-reload locally; rebuild images after dependency/Dockerfile changes. Validate rendered configuration and health endpoint after deployment.
