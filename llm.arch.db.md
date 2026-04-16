# DB Architecture — Schemas & Roles

## Schemas

| Schema | Purpose | Tables |
|--------|---------|--------|
| `public` | User-facing data | `workspaces`, `workspace_members`, `tables`, `rows` |
| `auth` | Authentication | `users`, `user_info` |
| `private` | DBA-only internal | `schema_migrations` |

## Roles

| Role | `public` | `auth` | `private` |
|------|----------|--------|-----------|
| `dba` | ALL (DDL+DML) | ALL (DDL+DML) | ALL (DDL+DML) |
| `app` | SELECT, INSERT, UPDATE, DELETE | SELECT only | — |
| `login_mgr` | — | SELECT, INSERT, UPDATE | — |

Grants use `ALTER DEFAULT PRIVILEGES FOR ROLE dba` so any future table
created by a dba-role user auto-inherits app/login grants. No post-hoc
regrant migration needed — V2 sets it up once.

`ALTER TABLE ... SET SCHEMA` does NOT trigger default privileges — V26
(moves users to auth) has explicit `GRANT` after the move.

## Login Users

| User | Role | Password source | Used by |
|------|------|-----------------|---------|
| `dba_user` | `dba` | **docker-compose.yml** (hardcoded) | Migration runner only |
| `app_user` | `app` | `POSTGRES_APP_PASSWORD` (.env) | General API |
| `login_user` | `login_mgr` | `POSTGRES_LOGIN_PASSWORD` (.env) | Login/auth endpoints |

Backend never sees DBA password. `.env` holds only app + login passwords.

## Backend Engine Mapping (`backend/src/core/db.py`)

```
app_engine    → app_user    → get_session         (search_path=public,auth)
login_engine  → login_user  → get_login_session   (search_path=auth)
```

Backend has no dba_engine. Migrations are a separate concern, run by the
`migration` profile container.

## Migration Tracking

`private.schema_migrations` — DBA-only. App/login roles cannot see or modify.

```sql
filename   VARCHAR PRIMARY KEY
checksum   VARCHAR NOT NULL DEFAULT ''     -- SHA-256 of file content
applied_at TIMESTAMP NOT NULL DEFAULT NOW()
```

Two integrity layers:
- `migration/checksums.txt` — committed, source of truth, verified before apply
- `private.schema_migrations.checksum` — DB-side hash, catches tampering after apply

## Row-Level Security (V27)

`public.tables` and `public.rows` have RLS enabled. Policies check workspace
membership via `check_workspace_member(workspace_id, app.current_user_id)`.

Backend's `get_rls_session` sets `app.current_user_id` via
`SELECT set_config('app.current_user_id', :uid, false)`. Persists across
commits on the same connection.

## Permission Tests

```bash
# app_user cannot DROP
docker compose exec db psql -U app_user -d db \
  -c "DROP TABLE public.rows;"
# → ERROR: must be owner

# app_user cannot INSERT auth
docker compose exec db psql -U app_user -d db \
  -c "INSERT INTO auth.users VALUES (...);"
# → ERROR: permission denied for table users

# login_user cannot read public
docker compose exec db psql -U login_user -d db \
  -c "SELECT 1 FROM public.rows;"
# → ERROR: permission denied

# app_user cannot see migrations
docker compose exec db psql -U app_user -d db \
  -c "SELECT * FROM private.schema_migrations;"
# → ERROR: permission denied for schema private
```
