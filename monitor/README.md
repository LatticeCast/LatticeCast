# Monitor

Optional observability stack, started only with the `monitor` profile:

```bash
docker compose --profile monitor up -d prometheus perses postgres-exporter
```

- Prometheus: http://127.0.0.1:${PROMETHEUS_PORT:-19090}
- Perses: http://127.0.0.1:${PERSES_PORT:-13000}

Config is mounted read-only into the containers:

- `prometheus/prometheus.yml` scrape targets
- `perses/config.yaml` server config; the file DB lives in the `perses_data` volume
- `perses/provisioning/` Prometheus datasource, project, and dashboards (YAML/JSON)

Perses reloads `provisioning/` on change and it overrides what is in the DB, so
keep dashboards as files here instead of editing them only in the UI.

Labels must stay low-cardinality: route templates, status class, pool name.
Never `workspace_id`, `user_id`, or raw URLs.
