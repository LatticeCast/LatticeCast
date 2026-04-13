# DB Architecture — Schemas & Roles

## Schemas

| Schema | Purpose | Tables |
|--------|---------|--------|
| `public` | User-facing data | `workspaces`, `workspace_members`, `tables`, `rows` |
| `auth` | Authentication | `users`, `user_info` |
| `private` | Internal / migrations | `schema_migrations` (future) |

## Roles

| Role | `public` | `auth` | `private` |
|------|----------|--------|-----------|
| `dba` | ALL (DDL+DML) | ALL (DDL+DML) | ALL (DDL+DML) |
| `app` | SELECT, INSERT, UPDATE, DELETE | SELECT only | — |
| `login_mgr` | — | SELECT, INSERT, UPDATE | — |

## Login Users (created by `postgres/init-roles.sh`)

| User | Role | Env var (password) | Used by |
|------|----|---------------------|---------|
| `dba_user` | `dba` | `POSTGRES_DBA_PASSWORD` | Migration runner at startup |
| `app_user` | `app` | `POSTGRES_APP_PASSWORD` | General API endpoints (FastAPI) |
| `login_user` | `login_mgr` | `POSTGRES_LOGIN_PASSWORD` | Login / auth endpoints |

## Table → Schema Mapping

```
public.workspaces
public.workspace_members
public.tables
public.rows

auth.users
auth.user_info

private.schema_migrations  (future)
```

## Role → Permission Matrix

| Operation | `dba_user` | `app_user` | `login_user` |
|-----------|-----------|-----------|-------------|
| CREATE/ALTER/DROP tables | ✅ all schemas | ❌ | ❌ |
| CRUD `public.*` | ✅ | ✅ | ❌ |
| SELECT `auth.*` | ✅ | ✅ | ✅ |
| INSERT/UPDATE `auth.*` | ✅ | ❌ | ✅ |
| DROP `auth.*` | ✅ | ❌ | ❌ |

## Backend Engine Mapping (`backend/src/core/db.py`)

```
dba_engine    → POSTGRES_DBA_PASSWORD   → migrations (Alembic / startup DDL)
app_engine    → POSTGRES_APP_PASSWORD   → general API sessions (get_session)
login_engine  → POSTGRES_LOGIN_PASSWORD → auth sessions (get_login_session)
```

Fallback: if a role password is not set, all engines fall back to the superuser connection.

## How to Test Permissions

```bash
# app_user should NOT be able to drop tables
docker compose exec db psql -U app_user -d db -c "DROP TABLE public.rows;"
# → ERROR: must be owner of table rows

# login_user should NOT be able to read public.rows
docker compose exec db psql -U login_user -d db -c "SELECT 1 FROM public.rows;"
# → ERROR: permission denied for table rows

# app_user should NOT be able to insert into auth.users
docker compose exec db psql -U app_user -d db -c "INSERT INTO auth.users VALUES (...);"
# → ERROR: permission denied for table users

# dba_user can do everything
docker compose exec db psql -U dba_user -d db -c "\dn+"
```
