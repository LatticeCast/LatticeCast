# Database and RLS

PostgreSQL owns identity, workspace authorization, table schemas, rows, views, and cache. `migration/V*.sql` is authoritative.

- `auth`: identities; `gdpr`: PII/password; `public`: workspaces, tables, views, rows; `private`: migration/cache state.
- `get_rls_session` sets `app.current_user_id`. `read` permits reads, `write` mutations, `owner` workspace administration.
- Normal routes use `app_engine`/`app_user`; login/admin uses `login_engine`/`mgr_user`.
- Row writes must use the PG mutation functions. Blob metadata uses `update_blob_cell`; ordinary patch/put must not mutate blob columns.
- Never edit an applied migration; add a new one and refresh `checksums.txt`.
