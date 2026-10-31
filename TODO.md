# TODO

## Token saving
use anthropic prompt caching.
agentic-hive need design caching prompt

## Performance Tuning

- [ ] Evaluate `gin_pending_list_limit` for GIN indexes on JSONB columns (select/tags)
  - Default 64KB may bottleneck during batch imports (CSV/JSON) and PM template creation
  - Consider per-index or session-level increase (e.g. 256KB) for bulk write scenarios
  - Trade-off: higher limit = faster writes, slightly slower queries on pending data

## Hardening (found in the v0.82.1 code review)

- [ ] `POST /login/password`: an account with no `gdpr.user_password` row is logged in without a password check (`router/api/auth.py`). `bootstrap_user` and the seeded `announcement` user create such accounts. Default to deny; require an explicit password-setup or admin-issued path
- [ ] Blob and `/storage` uploads read the whole file into memory with no size cap; downloads buffer the whole object (`router/api/rows.py`, `router/api/storage.py`). Add a size limit and stream
- [ ] `GET /tables` queries each workspace's tables and each table's schema separately (N+1)
- [ ] `put_blob_cell` holds one DB connection while `register_upload` opens a second; check pool exhaustion under concurrent uploads (pool 5 + 10 overflow per worker)
- [ ] `POST /tables/template/{kind}` checks `is_member` (read) and does not map `DBAPIError`; a read-only member probably gets a 500 instead of 403
- [ ] V20 `user_info_app_read USING (true)` lets any `app_user` query read every user's email; narrow it or serve lookups through a function
- [ ] Access token in `localStorage` (24 h default); `.env.example` sets `DEBUG_MODE=1`, which makes CORS `*`
- [ ] Seed functions (`_seed_blank`, `_seed_crm`, `_seed_pm`) still emit the legacy `doc` vocabulary and rely on `create_table_from_template` to normalize it to `blob`/`text`
