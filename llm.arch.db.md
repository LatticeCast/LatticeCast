# Database and RLS

PostgreSQL owns identity, workspace authorization, table schemas, rows, views, and cache. `migration/V*.sql` is authoritative.

- `auth`: identities; `gdpr`: PII/password; `public`: workspaces, tables, views, rows; `private`: migration/cache state.
- `get_rls_session` sets `app.current_user_id`. `read` permits reads, `write` mutations, `owner` workspace administration.
- Policies test membership of `current_user_workspaces(action)`, which is uncorrelated and so evaluated once per statement, not once per row. A member may read their own `workspace_members` rows; the full roster stays owner-only.
- Authorization is RLS's alone. `check_workspace_permission` exists only for `SECURITY DEFINER` functions doing DDL that RLS cannot govern; it is not callable by the app role.
- Normal routes use `app_engine`/`app_user`; login/admin uses `login_engine`/`mgr_user`.
- Row writes must use the PG mutation functions. Blob metadata uses `update_blob_cell`; ordinary patch/put must not mutate blob columns.
- A `BEFORE INSERT OR UPDATE OF row_data` trigger canonicalises `date`/`datetime` cells to epoch-millisecond integers and rejects the unparseable, so the invariant survives a raw `INSERT`.
- `row_id` comes from an atomic counter row in `private.table_row_counters`, never `MAX(row_id)+1`. Numbers are monotonic per table and never reused.
- Stored times are UTC+0 with no zone: `TIMESTAMP` columns, defaults `now() AT TIME ZONE 'UTC'`, database `timezone` pinned to UTC.
- Never edit an applied migration; add a new one and refresh `checksums.txt`.
