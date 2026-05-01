"""
test_migration_rls.py — Verify RLS policies exist after migrations.
"""

_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_WS_A = "11111111-1111-1111-1111-111111111111"
_WS_B = "22222222-2222-2222-2222-222222222222"


def _as_app(psql_fn, user_id: str, sql: str) -> str:
    """Run sql as app role with app.current_user_id pre-set via set_config.

    Three-statement sequence in one psql session:
      1. SELECT set_config(...)   — sets user context (as dba, persists)
      2. SET ROLE app             — switch to non-superuser so RLS applies
      3. <sql>                    — actual query with RLS active

    Returns the last digit-only line from psql output.  DML command tags
    like "INSERT 0 1", "UPDATE 1", "DELETE 1" follow RETURNING tuples and
    are NOT suppressed by --tuples-only, so we skip non-digit lines when
    searching in reverse.  For SELECT COUNT(*) the count is also numeric.
    Falls back to the last non-blank line if no digit line is found.
    """
    result = psql_fn(
        f"SELECT set_config('app.current_user_id', '{user_id}', false); "
        f"SET ROLE app; "
        f"{sql}"
    )
    lines = [ln.strip() for ln in result.strip().split("\n") if ln.strip()]
    for line in reversed(lines):
        if line.isdigit():
            return line
    return lines[-1] if lines else ""


def verify(psql_fn) -> list[str]:
    errors: list[str] = []

    # Structural: RLS enabled
    for table in ("rows", "tables", "table_views"):
        result = psql_fn(
            f"SELECT rowsecurity FROM pg_tables "
            f"WHERE schemaname='public' AND tablename='{table}';"
        )
        if "t" not in (result or ""):
            errors.append(f"RLS NOT ENABLED: public.{table}")

    # Structural: policies exist
    for table, policy in [
        ("tables", "tables_workspace_member"),
        ("rows", "rows_workspace_member"),
        ("table_views", "table_views_workspace_member"),
    ]:
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

    # Behavioral: two users in two workspaces
    # Insert users, workspaces, membership, and tables.
    # V34 trigger trg_tables_create_schema_and_order auto-inserts the
    # __schema__ and __order__ rows for each new table.
    psql_fn(
        f"INSERT INTO auth.users (user_id, role) VALUES "
        f"('{_USER_A}'::uuid,'user'),('{_USER_B}'::uuid,'user') "
        f"ON CONFLICT (user_id) DO NOTHING; "
        f"INSERT INTO public.user_info (user_id, user_name) VALUES "
        f"('{_USER_A}'::uuid,'tv_rls_a'),('{_USER_B}'::uuid,'tv_rls_b') "
        f"ON CONFLICT (user_id) DO NOTHING; "
        f"INSERT INTO public.workspaces (workspace_id, workspace_name) VALUES "
        f"('{_WS_A}'::uuid,'tv_rls_wsa'),('{_WS_B}'::uuid,'tv_rls_wsb') "
        f"ON CONFLICT (workspace_id) DO NOTHING; "
        f"INSERT INTO public.workspace_members (workspace_id, user_id, role) "
        f"VALUES ('{_WS_A}'::uuid,'{_USER_A}'::uuid,'owner'),"
        f"('{_WS_B}'::uuid,'{_USER_B}'::uuid,'owner') "
        f"ON CONFLICT (workspace_id, user_id) DO NOTHING; "
        f"INSERT INTO public.tables (workspace_id, table_id) VALUES "
        f"('{_WS_A}'::uuid,'tv_rls_tbl_a'),"
        f"('{_WS_B}'::uuid,'tv_rls_tbl_b') "
        f"ON CONFLICT (workspace_id, table_id) DO NOTHING"
    )

    # SELECT positive: user A can see own workspace views (auto-created by trigger)
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id = '{_WS_A}'::uuid;",
    )
    if not count.isdigit() or int(count) == 0:
        errors.append(
            "RLS BEHAVIORAL: user A cannot SELECT from own workspace table_views"
        )

    # SELECT isolation: user A cannot see workspace B views
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id = '{_WS_B}'::uuid;",
    )
    if count.isdigit() and int(count) > 0:
        errors.append(
            "RLS BEHAVIORAL: user A can SELECT from workspace B table_views"
        )

    # INSERT positive: user A can insert a kanban view into workspace A
    # _as_app returns the last digit-only line; we use a count(*) probe
    # afterward to verify the row landed.
    _as_app(
        psql_fn,
        _USER_A,
        f"INSERT INTO public.table_views "
        f"(workspace_id, table_id, name, type, config) "
        f"VALUES ('{_WS_A}'::uuid,'tv_rls_tbl_a',"
        f"'rls_test_view','kanban','{{}}');",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid AND name='rls_test_view';",
    )
    if not count.isdigit() or int(count) != 1:
        errors.append(
            "RLS BEHAVIORAL: user A cannot INSERT into own workspace table_views"
        )

    # UPDATE positive: user A can update the view just inserted
    _as_app(
        psql_fn,
        _USER_A,
        f"UPDATE public.table_views SET type='timeline' "
        f"WHERE workspace_id='{_WS_A}'::uuid AND name='rls_test_view';",
    )
    type_after = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT 1 FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid "
        f"  AND name='rls_test_view' AND type='timeline';",
    )
    if type_after != "1":
        errors.append(
            "RLS BEHAVIORAL: user A cannot UPDATE in own workspace table_views"
        )

    # DELETE positive: user A can delete the non-schema view
    _as_app(
        psql_fn,
        _USER_A,
        f"DELETE FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid AND name='rls_test_view';",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid AND name='rls_test_view';",
    )
    if count != "0":
        errors.append(
            "RLS BEHAVIORAL: user A cannot DELETE in own workspace table_views"
        )

    return errors
