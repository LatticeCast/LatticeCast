# LatticeCast — Database Architecture

PostgreSQL stores identity, authorization, table schemas, rows, views, and the
application cache. MinIO stores document bodies.

## Source of Truth

- DDL and functions: `migration/V*.sql`
- Expected/forbidden shape: `migration/test_migration_schema.py`
- RLS behavior: `migration/test_migration_rls.py`
- Migration ordering and checksums: `migration/migrate.py`,
  `migration/checksums.txt`
- Runtime access: `backend/src/models/` and `backend/src/repository/`

## Schemas and Tables

| Schema | Tables | Purpose |
|---|---|---|
| `auth` | `users` | UUID identity and application role |
| `gdpr` | `user_info`, `user_password` | PII, handle, config, optional credential |
| `public` | `workspaces`, `workspace_members` | Workspace identity and access grants |
| `public` | `tables`, `table_views`, `rows` | Generic table engine |
| `private` | `schema_migrations`, `cache` | Migration state and UNLOGGED TTL cache |

## Core Keys and Shapes

| Relation | Identity | Important data |
|---|---|---|
| `workspaces` | `workspace_id UUID` | `workspace_name` is a display/path alias |
| `workspace_members` | `(workspace_id, user_id, action)` | one row per `read`/`write`/`owner` action |
| `tables` | `(workspace_id, table_id)` | `config JSONB` contains columns and view metadata |
| `table_views` | `(workspace_id, table_id, view_id)` | view name/type/options in `config JSONB` |
| `rows` | `(workspace_id, table_id, row_id)` | `row_data JSONB`, keyed by column UUID |

`row_id` and `view_id` are numeric and allocated per table. Rows and views have
composite foreign keys to tables with cascade behavior.

`tables.config` is the schema cache returned to the frontend. Its stable fields
are `columns`, `view_order`, and `default_view`; API responses also attach the
ordered view rows. Exact JSON shape belongs to the PG functions, repository,
and response models rather than this overview.

## Authorization

`get_rls_session` sets `app.current_user_id` for the request. Policies use
materialized workspace actions:

| Level exposed by API | Stored action rows |
|---|---|
| `read` | `read` |
| `write` | `read`, `write` |
| `owner` | `read`, `write`, `owner` |

Workspace data SELECT uses `read`; data INSERT/UPDATE/DELETE uses `write`;
workspace/member administration uses `owner`. Repository helpers aggregate the
action rows back into one level for API responses.

## Database Roles and Engines

| Engine | Login role | Purpose |
|---|---|---|
| `app_engine` | `app_user` | General API under RLS |
| `login_engine` | `mgr_user` | Login/admin paths with `BYPASSRLS` |
| migration runner | `dba_user` | DDL, verification, migration tracking |

Both application engines are async and configured in `backend/src/core/db.py`.

## PG-Owned Operations

SECURITY DEFINER functions own atomic workspace creation, access grants,
sidebar aggregation, column/view/schema mutation, template creation, and
row-data index management. Backend repositories are thin callers and then read
the canonical result.

## Invariants and Gotchas

- `workspace_id`, not `workspace_name` or `user_name`, is the workspace key.
- `workspace_name` and `table_id` cannot contain `.` because they are URL/S3
  path-facing values.
- The same `table_id` may exist in different workspaces.
- `user_password` is not readable through the app role.
- RLS is the authorization boundary; route-level membership checks are not a
  substitute for policies.
- Before any migration command, create the dump required by `migrate.py`. Never
  edit an applied migration; add a new migration and refresh checksums.
