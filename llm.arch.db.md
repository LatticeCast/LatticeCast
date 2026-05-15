# DB Architecture — Schemas & Roles

## Schemas

| Schema | Purpose | Tables |
|--------|---------|--------|
| `public` | User-facing data | `workspaces`, `workspace_members`, `tables`, `table_schemas`, `table_views`, `rows` |
| `auth` | Identity only | `users` (UUID + role) |
| `gdpr` | PII (GDPR-purge boundary) | `user_info` (email, user_name, config) |
| `private` | DBA-only internal | `schema_migrations` |

V40 PII merge: the old `public.user_info` + `auth.gdpr` split is gone. All
user PII (email, user_name, profile config) lives in one row in
`gdpr.user_info`. A GDPR purge drops that row (or the entire schema) without
touching `auth.users` or workspace audit trails.

`public.table_schemas` holds the schema state for each table — columns,
view_order, default_view — as a single JSONB document. `public.table_views`
holds the individual view configs. Both are auto-created by trigger on
`public.tables` INSERT.

## Roles

| Role | `public` | `auth` | `gdpr` | `private` |
|------|----------|--------|--------|-----------|
| `dba` | ALL (DDL+DML) | ALL (DDL+DML) | ALL (DDL+DML) | ALL (DDL+DML) |
| `mgr` | SELECT, INSERT, UPDATE, DELETE | SELECT, INSERT, UPDATE, DELETE | SELECT, INSERT, UPDATE, DELETE | SELECT, INSERT, UPDATE, DELETE |
| `app` | SELECT, INSERT, UPDATE, DELETE | SELECT only | SELECT, UPDATE (own row via RLS) | — |

`mgr` has `BYPASSRLS` — admin/login paths see all rows regardless of
`app.current_user_id`. `app` goes through RLS normally.

**V15 explicit grants:** `ALTER DEFAULT PRIVILEGES FOR ROLE dba` only covers
objects created by the `dba` group role. Migration runner connects as
`dba_user` (a login user that inherits `dba`), so tables are owned by
`dba_user` — not `dba` — and the default-priv machinery silently skips them.
V15 re-grants table-level DML to `app` and `mgr` on all three schemas
explicitly.

## Login Users

| User | Role | Password source | Used by |
|------|------|-----------------|---------|
| `dba_user` | `dba` | **docker-compose.yml** (hardcoded) | Migration runner only |
| `app_user` | `app` | `POSTGRES_APP_PASSWORD` (.env) | General API |
| `mgr_user` | `mgr` | `POSTGRES_MGR_PASSWORD` (.env) | Login/auth endpoints |

Backend never sees DBA password. `.env` holds only app + mgr passwords.
`mgr_user` has `BYPASSRLS` set directly on the role (PG role attributes are
not inherited through `GRANT mgr TO mgr_user` — V15 sets it explicitly).

## Backend Engine Mapping (`backend/src/core/db.py`)

```
app_engine    → app_user    → get_session         (search_path=public,auth,gdpr)
login_engine  → mgr_user    → get_login_session   (search_path=public,auth,gdpr)
```

Both engines include `gdpr` on `search_path` (v40) so unqualified joins to
`gdpr.user_info` work without schema-qualifying every query. Backend has no
dba_engine — migrations are a separate concern, run by the `migration` profile
container.

## Migration Tracking

`private.schema_migrations` — DBA-only. App/mgr roles cannot see or modify.

```sql
filename   VARCHAR PRIMARY KEY
checksum   VARCHAR NOT NULL DEFAULT ''     -- SHA-256 of file content
applied_at TIMESTAMP NOT NULL DEFAULT NOW()
```

Two integrity layers:
- `migration/checksums.txt` — committed, source of truth, verified before apply
- `private.schema_migrations.checksum` — DB-side hash, catches tampering after apply

V1–V18 is the locked baseline (squashed pre-AWS). V15+ is forward-only forever.

## Row-Level Security

RLS is enabled on all user-facing tables. Two policy shapes:

| Table | Policy | Filter |
|-------|--------|--------|
| `gdpr.user_info` | self only | `user_id = current_user_id` |
| `public.workspaces` | workspace member | `check_workspace_member(workspace_id, current_user_id)` |
| `public.workspace_members` | workspace member | same |
| `public.tables` | workspace member | same |
| `public.table_schemas` | workspace member | same |
| `public.table_views` | workspace member | same |
| `public.rows` | workspace member | same |

`mgr` bypasses all RLS (BYPASSRLS attribute). `app` must have
`app.current_user_id` set via `get_rls_session` before any data access.

`check_workspace_member()` is `SECURITY DEFINER` to avoid infinite recursion
(the function queries `workspace_members`, which itself has an RLS policy that
calls the function).

Backend's `get_rls_session` sets `app.current_user_id` via
`SELECT set_config('app.current_user_id', :uid, false)`. Persists across
commits on the same connection. Pool reset (`DISCARD ALL`) clears it on
connection return.

## Permission Tests

```bash
# app_user cannot DROP
docker compose exec db psql -U app_user -d db \
  -c "DROP TABLE public.rows;"
# → ERROR: must be owner

# app_user cannot write auth
docker compose exec db psql -U app_user -d db \
  -c "INSERT INTO auth.users VALUES (gen_random_uuid(), 'user');"
# → ERROR: permission denied for table users

# mgr_user can read auth (BYPASSRLS)
docker compose exec db psql -U mgr_user -d db \
  -c "SELECT user_id FROM auth.users LIMIT 1;"
# → (rows)

# app_user cannot see migrations
docker compose exec db psql -U app_user -d db \
  -c "SELECT * FROM private.schema_migrations;"
# → ERROR: permission denied for schema private
```
