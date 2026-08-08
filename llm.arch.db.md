# DB Architecture

## Source of Truth

- **Schema definition:** `migration/V*.sql` (V1–V33) — CREATE TABLE + CREATE OR REPLACE FUNCTION
- **Schema verification:** `migration/test_migration_schema.py` — `EXPECTED_COLUMNS` / `FORBIDDEN_COLUMNS`
- **RLS verification:** `migration/test_migration_rls.py` — behavioral tests
- **Roles & grants:** `migration/V1__init.sql` (roles), `migration/V15__grants_app.sql` (explicit grants)

## Schemas

| Schema | Purpose |
|--------|---------|
| `public` | workspaces, workspace_members, tables, table_views, rows |
| `auth` | users (identity only — user_id, role, timestamps) |
| `gdpr` | user_info (PII/config) + user_password (optional credential) |
| `private` | schema_migrations + UNLOGGED cache |

## Roles & Login Users

| Role | Type | Privileges |
|------|------|------------|
| `dba` | group | DDL on all schemas. No DML on data tables. |
| `mgr` | group, BYPASSRLS | DML on all schemas. No DDL. |
| `app` | group | CRUD public, SELECT auth, SELECT+UPDATE gdpr (RLS-limited) |
| `dba_user` | login (superuser) | Inherits dba. Owns all objects. Runs migrations. |
| `mgr_user` | login, BYPASSRLS | Inherits mgr. Auth/admin backend. Env: `POSTGRES_MGR_PASSWORD` |
| `app_user` | login | Inherits app. End-user sessions via RLS. |

## Engines (`backend/src/core/db.py`)

| Engine | PG User | search_path | Used by |
|--------|---------|-------------|---------|
| `app_engine` | app_user | `public,auth,gdpr` | General API (CRUD public, SELECT auth) |
| `login_engine` | mgr_user | `public,auth,gdpr` | Auth endpoints (CRUD auth, BYPASSRLS) |

Both: pool_size=5, max_overflow=10, async (asyncpg).

## Tables

| Table | PK | Key columns | RLS |
|-------|-----|-------------|-----|
| `auth.users` | `user_id` UUID | role, timestamps | — |
| `gdpr.user_info` | `user_id` UUID (FK→users) | email (unique), user_name (unique, `^[a-z0-9][a-z0-9_-]{2,31}$`), config JSONB | self-only |
| `gdpr.user_password` | `user_id` UUID (FK→user_info) | password_hash, updated_at | no app grant; mgr only |
| `public.workspaces` | `workspace_id` UUID | workspace_name | read grant to SELECT; owner to mutate |
| `public.workspace_members` | `(workspace_id, user_id, action)` | action = read/write/owner | owner-only, including SELECT |
| `public.tables` | `(workspace_id, table_id)` | config JSONB, created_by, updated_by | read to SELECT; write to mutate |
| `public.table_views` | `(workspace_id, table_id, view_id)` | config JSONB, view_id auto-increment trigger | read/write split |
| `public.rows` | `(workspace_id, table_id, row_id)` | row_data JSONB, row_id auto-increment trigger | read/write split |
| `private.schema_migrations` | `filename` | checksum, applied_at | — |
| `private.cache` | `key` | value JSONB, expires_at | UNLOGGED PG cache |

`tables.config` JSONB shape: `{columns: [...], view_order: [view_id, ...], default_view: view_id|0|null}`. Repository/API responses normalize null to `0`.

FK cascades: rows→tables and table_views→tables have `ON DELETE CASCADE ON UPDATE CASCADE` (V30).

## RLS (`V10`, rewritten by `V33`)

`get_rls_session` sets session var `app.current_user_id` (UUID) per request.
`check_workspace_permission(ws_id, user_id, action)` is SECURITY DEFINER/STABLE
to avoid recursive policy evaluation. An owner is three materialized rows
(`read`, `write`, `owner`); write is two; read is one. `workspace_members`
is owner-visible only. Workspace data uses `read` for SELECT and `write` for
INSERT/UPDATE/DELETE; workspace rename/delete requires `owner`.

## PG Functions (SECURITY DEFINER)

| Function | Source | Purpose |
|----------|--------|---------|
| `add_column` / `update_column` / `delete_column` | V23 | Column CRUD on tables.config.columns |
| `update_col_order` / `update_view_order` / `update_default_view` | V23 | Reorder columns/views, set default view |
| `create_view` / `update_view` / `delete_view` | V23 | View CRUD on table_views + tables.config |
| `create_table_from_template` | V27 | Dispatch to `_seed_blank`/`_seed_pm`/`_seed_crm`/`_seed_workflow` |
| `create_workspace` | V17/V33 | Atomic workspace + creator's three action grants (RLS bypass) |
| `check_workspace_permission` | V33 | Flat action lookup used by RLS policies |
| `grant_workspace_action` | V33 | Atomically materialize a read/write/owner level; invoker remains subject to RLS |
| `create_row_data_index` / `drop_row_data_index` | V11 | Auto-managed per-column indexes (btree/GIN) |

## Key Migration Milestones

| Migration | What changed |
|-----------|--------------|
| V1–V7 | Base schema: roles, users, user_info, workspaces, members, tables, rows |
| V8–V9 | table_schemas + table_views (both 1:1 with tables) |
| V10–V11 | RLS policies + per-column index helpers |
| V12–V14 | Template seeders + schema/view CRUD functions |
| V15 | Explicit grants fixing default-priv gap; mgr_user BYPASSRLS |
| V17 | `create_workspace` atomic function |
| V23 | **Merge table_schemas → tables.config** — all PG functions rewritten |
| V24–V26 | User table schemas, default_view=0 allowed, view type check |
| V27–V28 | Workflow template (`_seed_workflow`), drop title col |
| V29 | Backfill default_view to 0 and normalize null in its update function; blank/default configs can still store null |
| V30 | FK ON UPDATE CASCADE on rows + table_views |
| V31 | PostgreSQL UNLOGGED cache replaces external cache service |
| V32 | Optional `gdpr.user_password`; only mgr/login session can access it |
| V33 | Replace member roles with action grants; split RLS into read/write/owner policies |

## Migration Commands

```bash
docker compose --profile migration run --rm --entrypoint python migration migrate.py --test-only  # test
docker compose --profile migration run --rm --entrypoint python migration migrate.py --hash       # regen checksums
docker compose --profile migration run --rm --entrypoint python migration migrate.py --dump       # dump first!
docker compose --profile migration run --rm --entrypoint python migration migrate.py --apply-only # apply
```
