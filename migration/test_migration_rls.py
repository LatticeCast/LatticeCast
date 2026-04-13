"""
test_migration_rls.py — Verify RLS policies exist after migrations.
Called by test_migrations.py (not standalone).
"""


def verify(psql_fn) -> list[str]:
    """Run RLS checks. Returns list of error strings (empty = pass)."""
    errors: list[str] = []

    # Check RLS enabled on rows and tables
    for table in ("rows", "tables"):
        result = psql_fn(
            f"SELECT rowsecurity FROM pg_tables "
            f"WHERE schemaname='public' AND tablename='{table}';"
        )
        if "t" not in (result or ""):
            errors.append(f"RLS NOT ENABLED: public.{table}")

    # Check policies exist
    for table, policy in [("tables", "tables_workspace_member"), ("rows", "rows_workspace_member")]:
        result = psql_fn(
            f"SELECT 1 FROM pg_policies "
            f"WHERE tablename='{table}' AND policyname='{policy}';"
        )
        if not result:
            errors.append(f"MISSING POLICY: {table}.{policy}")

    # Check helper functions exist
    for func in ("check_workspace_member", "get_table_workspace_id"):
        result = psql_fn(
            f"SELECT 1 FROM pg_proc WHERE proname='{func}';"
        )
        if not result:
            errors.append(f"MISSING FUNCTION: {func}")

    return errors
