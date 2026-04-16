"""
test_migration_rls.py — Verify RLS policies exist after migrations.
"""


def verify(psql_fn) -> list[str]:
    errors: list[str] = []

    for table in ("rows", "tables"):
        result = psql_fn(
            f"SELECT rowsecurity FROM pg_tables "
            f"WHERE schemaname='public' AND tablename='{table}';"
        )
        if "t" not in (result or ""):
            errors.append(f"RLS NOT ENABLED: public.{table}")

    for table, policy in [("tables", "tables_workspace_member"), ("rows", "rows_workspace_member")]:
        result = psql_fn(
            f"SELECT 1 FROM pg_policies "
            f"WHERE tablename='{table}' AND policyname='{policy}';"
        )
        if not result:
            errors.append(f"MISSING POLICY: {table}.{policy}")

    for func in ("check_workspace_member",):
        result = psql_fn(f"SELECT 1 FROM pg_proc WHERE proname='{func}';")
        if not result:
            errors.append(f"MISSING FUNCTION: {func}")

    return errors
