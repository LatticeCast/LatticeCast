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

    # Structural: policies exist (V33: read/write split, no more single
    # *_workspace_member policy)
    for table, policy in [
        ("tables", "tables_read"),
        ("tables", "tables_write_insert"),
        ("rows", "rows_read"),
        ("rows", "rows_write_insert"),
        ("table_views", "table_views_read"),
        ("table_views", "table_views_write_insert"),
    ]:
        result = psql_fn(
            f"SELECT 1 FROM pg_policies "
            f"WHERE tablename='{table}' AND policyname='{policy}';"
        )
        if not result:
            errors.append(f"MISSING POLICY: {table}.{policy}")

    for func in ("check_workspace_permission", "grant_workspace_action"):
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
        f"INSERT INTO gdpr.user_info (user_id, email, user_name) VALUES "
        f"('{_USER_A}'::uuid,'tv_rls_a@example.com','tv_rls_a'),"
        f"('{_USER_B}'::uuid,'tv_rls_b@example.com','tv_rls_b') "
        f"ON CONFLICT (user_id) DO NOTHING; "
        f"INSERT INTO public.workspaces (workspace_id, workspace_name) VALUES "
        f"('{_WS_A}'::uuid,'tv_rls_wsa'),('{_WS_B}'::uuid,'tv_rls_wsb') "
        f"ON CONFLICT (workspace_id) DO NOTHING; "
        f"INSERT INTO public.workspace_members (workspace_id, user_id, action) "
        f"VALUES "
        f"('{_WS_A}'::uuid,'{_USER_A}'::uuid,'read'),"
        f"('{_WS_A}'::uuid,'{_USER_A}'::uuid,'write'),"
        f"('{_WS_A}'::uuid,'{_USER_A}'::uuid,'owner'),"
        f"('{_WS_B}'::uuid,'{_USER_B}'::uuid,'read'),"
        f"('{_WS_B}'::uuid,'{_USER_B}'::uuid,'write'),"
        f"('{_WS_B}'::uuid,'{_USER_B}'::uuid,'owner') "
        f"ON CONFLICT (workspace_id, user_id, action) DO NOTHING; "
        f"INSERT INTO public.tables (workspace_id, table_id) VALUES "
        f"('{_WS_A}'::uuid,'tv_rls_tbl_a'),"
        f"('{_WS_B}'::uuid,'tv_rls_tbl_b') "
        f"ON CONFLICT (workspace_id, table_id) DO NOTHING"
    )

    # SELECT positive: user A can see own workspace tables row
    # (V23: table_schemas merged into tables — config lives here now)
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.tables "
        f"WHERE workspace_id = '{_WS_A}'::uuid;",
    )
    if not count.isdigit() or int(count) == 0:
        errors.append(
            "RLS BEHAVIORAL: user A cannot SELECT from own workspace tables"
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

    # v40: table_views.name and .type are gone — they live inside config
    # JSONB. view_id is auto-assigned by trg_set_view_id_fn (DEFAULT 0
    # sentinel after V16). Filter by config->>'name' for behavioral
    # assertions.
    _test_name = "rls_test_view"

    # INSERT positive: user A can insert a kanban view into workspace A.
    _as_app(
        psql_fn,
        _USER_A,
        f"INSERT INTO public.table_views "
        f"(workspace_id, table_id, config) "
        f"VALUES ('{_WS_A}'::uuid,'tv_rls_tbl_a',"
        f"""'{{"name":"{_test_name}","type":"kanban"}}'::jsonb);""",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid "
        f"  AND config->>'name'='{_test_name}';",
    )
    if not count.isdigit() or int(count) != 1:
        errors.append(
            "RLS BEHAVIORAL: user A cannot INSERT into own workspace table_views"
        )

    # UPDATE positive: user A can update the view's config.
    _as_app(
        psql_fn,
        _USER_A,
        f"""UPDATE public.table_views """
        f"""SET config = config || '{{"type":"timeline"}}'::jsonb """
        f"""WHERE workspace_id='{_WS_A}'::uuid """
        f"""  AND config->>'name'='{_test_name}';""",
    )
    type_after = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT 1 FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid "
        f"  AND config->>'name'='{_test_name}' "
        f"  AND config->>'type'='timeline';",
    )
    if type_after != "1":
        errors.append(
            "RLS BEHAVIORAL: user A cannot UPDATE in own workspace table_views"
        )

    # DELETE positive: user A can delete the view.
    _as_app(
        psql_fn,
        _USER_A,
        f"DELETE FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid "
        f"  AND config->>'name'='{_test_name}';",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE workspace_id='{_WS_A}'::uuid "
        f"  AND config->>'name'='{_test_name}';",
    )
    if count != "0":
        errors.append(
            "RLS BEHAVIORAL: user A cannot DELETE in own workspace table_views"
        )

    # V33: workspace_members is owner-only, even for SELECT. Both seeded
    # users hold 'owner' on their own workspace, so this is a
    # same-workspace-different-owner-only check: user A has no grant of
    # any kind on workspace B, so this doubles as a membership-visibility
    # isolation check too.
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.workspace_members "
        f"WHERE workspace_id = '{_WS_A}'::uuid;",
    )
    if not count.isdigit() or int(count) == 0:
        errors.append(
            "RLS BEHAVIORAL: owner cannot SELECT own workspace_members"
        )

    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.workspace_members "
        f"WHERE workspace_id = '{_WS_B}'::uuid;",
    )
    if count.isdigit() and int(count) > 0:
        errors.append(
            "RLS BEHAVIORAL: user A can SELECT workspace B's workspace_members"
        )

    return errors
