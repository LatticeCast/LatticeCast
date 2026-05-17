# DB Architecture (v0.45)

## Source of Truth

- **Schema definition:** `migration/V*.sql` — read the CREATE TABLE and CREATE OR REPLACE FUNCTION statements directly
- **Schema verification:** `migration/test_migration_schema.py` — `EXPECTED_COLUMNS` and `FORBIDDEN_COLUMNS` lists define the exact current schema shape
- **RLS verification:** `migration/test_migration_rls.py` — behavioral tests for row-level security
- **Roles & grants:** `migration/V1__init.sql` (roles), `migration/V15__grants_app.sql` (grants)

## Key Migration Milestones

| Migration | What changed |
|-----------|--------------|
| V1–V7 | Base schema: users, workspaces, tables, rows |
| V8–V9 | table_schemas + table_views (1:1 with tables) |
| V10 | RLS policies on all user-facing tables |
| V11 | Per-column auto-index helpers (SECURITY DEFINER) |
| V12 | Template seeders (blank/pm/crm) |
| V13 | Schema mutation PG functions (add/update/delete column, col_order, view_order, default_view) |
| V14 | View CRUD PG functions (create/update/delete view) |
| V18 | `immutable_iso_to_ts` for date btree indexes |
| V19 | `update_view` null-patch removes keys |
| V22 | Fix `delete_column` bool_or bug |
| V23 | **Merge `table_schemas` into `tables`** — all 10 PG functions rewritten |

## Migration Commands

```bash
# Test only (no apply to live DB)
docker compose --profile migration run --rm --entrypoint python migration migrate.py --test-only

# Regenerate checksums after editing SQL
docker compose --profile migration run --rm --entrypoint python migration migrate.py --hash

# ALWAYS dump before applying
docker compose --profile migration run --rm --entrypoint python migration migrate.py --dump

# Apply to live DB
docker compose --profile migration run --rm --entrypoint python migration migrate.py --apply-only
```
