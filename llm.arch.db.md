# DB Architecture

## Source of Truth

- **Schema definition:** `migration/V*.sql` (V1–V30) — CREATE TABLE + CREATE OR REPLACE FUNCTION
- **Schema verification:** `migration/test_migration_schema.py` — `EXPECTED_COLUMNS` / `FORBIDDEN_COLUMNS`
- **RLS verification:** `migration/test_migration_rls.py` — behavioral tests
- **Roles & grants:** `migration/V1__init.sql` (roles), `migration/V15__grants_app.sql` (explicit grants)

## Schemas

| Schema | Purpose |
|--------|---------|
| `public` | workspaces, workspace_members, tables, table_views, rows |
| `auth` | users (identity only — user_id, role, timestamps) |
| `gdpr` | user_info (PII: email, user_name, config JSONB) |
| `private` | schema_migrations tracking only |

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
| `public.workspaces` | `workspace_id` UUID | workspace_name | member-only |
| `public.workspace_members` | `(workspace_id, user_id)` | role (owner/member) | member-only |
| `public.tables` | `(workspace_id, table_id)` | config JSONB, created_by, updated_by | member-only |
| `public.table_views` | `(workspace_id, table_id, view_id)` | config JSONB, view_id auto-increment trigger | member-only |
| `public.rows` | `(workspace_id, table_id, row_id)` | row_data JSONB, row_id auto-increment trigger | member-only |
| `private.schema_migrations` | `filename` | checksum, applied_at | — |

`tables.config` JSONB shape: `{columns: [...], view_order: [view_id, ...], default_view: view_id|0}`

FK cascades: rows→tables and table_views→tables have `ON DELETE CASCADE ON UPDATE CASCADE` (V30).

## RLS (`V10`)

Session var `app.current_user_id` (UUID) set per request. Helper: `check_workspace_member(ws_id, u_id)` — SECURITY DEFINER, STABLE.

## PG Functions (SECURITY DEFINER)

| Function | Source | Purpose |
|----------|--------|---------|
| `add_column` / `update_column` / `delete_column` | V23 | Column CRUD on tables.config.columns |
| `update_col_order` / `update_view_order` / `update_default_view` | V23 | Reorder columns/views, set default view |
| `create_view` / `update_view` / `delete_view` | V23 | View CRUD on table_views + tables.config |
| `create_table_from_template` | V27 | Dispatch to `_seed_blank`/`_seed_pm`/`_seed_crm`/`_seed_workflow` |
| `create_workspace` | V17 | Atomic workspace + owner member (RLS bypass) |
| `create_row_data_index` / `drop_row_data_index` | V11 | Auto-managed per-column indexes (btree/GIN) |
| `check_workspace_member` | V10 | RLS helper |

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
| V29 | default_view NOT NULL (0 = no default) |
| V30 | FK ON UPDATE CASCADE on rows + table_views |

## Migration Commands

```bash
docker compose --profile migration run --rm --entrypoint python migration migrate.py --test-only  # test
docker compose --profile migration run --rm --entrypoint python migration migrate.py --hash       # regen checksums
docker compose --profile migration run --rm --entrypoint python migration migrate.py --dump       # dump first!
docker compose --profile migration run --rm --entrypoint python migration migrate.py --apply-only # apply
```
