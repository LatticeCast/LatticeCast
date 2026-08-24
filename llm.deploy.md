# Deployment

`docker-compose.yml` is the local runtime source; `k8s/` contains cluster manifests.

```text
nginx -> frontend + backend -> PostgreSQL + S3-compatible storage
```

- `.env.example` documents settings; never commit or log real values.
- Backend storage configuration must match an IAM/bucket policy granting bucket listing plus object read/write/delete for its configured bucket.
- Run migrations through the migration service before deploying code that depends on them.
- Source mounts hot-reload locally; rebuild images after dependency/Dockerfile changes. Validate rendered configuration and health endpoint after deployment.
