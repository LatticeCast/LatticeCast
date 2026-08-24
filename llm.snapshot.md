# Snapshots

Use the E2E browser to prove rendered behavior, not just an HTTP success.

```bash
docker compose --profile test up -d browser e2e
docker compose --profile test exec e2e pytest path/to/test.py -v --snapshot
```

- Authenticate with the helpers in `e2e/e2e_base.py`, then wait for the target observable state.
- Save to `/output/<name>.png`; the host sees `.browser/<name>.png`.
- Use deterministic viewport/data and inspect the image. Do not use fixed waits or leave credentials in scripts/artifacts.
