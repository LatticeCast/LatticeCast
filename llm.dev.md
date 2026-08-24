# Development

```bash
docker compose up -d db minio
docker compose --profile migration run --rm migration
docker compose up -d
docker compose exec frontend npm run check
docker compose exec frontend npm run build
docker compose exec backend ruff check src
```

- Frontend changes: type-check/build and focused E2E/snapshot.
- Backend changes: Ruff and focused API/E2E test.
- DB: never alter an applied migration. Before a migration: `--dump`, `--test-only`, `--hash`, then apply via `migration/migrate.py`.
- Tests use the live Compose stack; wait on observable state, never sleeps.
- Rebuild after dependency/Dockerfile changes. Source changes hot-reload locally.
