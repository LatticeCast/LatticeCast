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

    # V71: child policies resolve the caller's legal table ids from the
    # workspace grants instead of trusting a workspace_id on the child row.
    for table in ("rows", "table_views"):
        result = psql_fn(
            "SELECT qual FROM pg_policies "
            "WHERE schemaname='public' "
            f"  AND tablename='{table}' "
            f"  AND policyname='{table}_read';"
        )
        if "current_user_tables" not in result:
            errors.append(f"RLS POLICY: {table}_read is not table-set based (V71)")

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
        f"INSERT INTO public.tables (workspace_id, table_name) VALUES "
        f"('{_WS_A}'::uuid,'tv_rls_tbl_a'),"
        f"('{_WS_B}'::uuid,'tv_rls_tbl_b') "
        f"ON CONFLICT (workspace_id, table_name) DO NOTHING"
    )

    # V46: sidebar identity comes only from app.current_user_id. User A owns
    # one workspace with one table despite holding three action rows.
    sidebar_counts = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT jsonb_array_length(payload->'workspaces') || ',' || "
        f"jsonb_array_length(payload->'tables') "
        f"FROM (SELECT public.get_user_sidebar() payload) s;"
    ).strip()
    if sidebar_counts != "1,1":
        errors.append(
            "SIDEBAR BEHAVIORAL: action grants multiply payload rows "
            f"(expected 1,1 got {sidebar_counts!r})"
        )

    # A self-service workspace function must bind the owner from the RLS
    # context instead of accepting a caller-controlled user UUID.
    created_workspace_id = _as_app(
        psql_fn,
        _USER_A,
        "SELECT public.create_workspace('tv_rls_context_created') ->> 'workspace_id';",
    )
    created_actions = psql_fn(
        "SELECT string_agg(action, ',' ORDER BY action) "
        "FROM public.workspace_members "
        f"WHERE workspace_id = '{created_workspace_id}'::UUID "
        f"AND user_id = '{_USER_A}'::UUID;"
    ).strip()
    if created_actions != "owner,read,write":
        errors.append(
            "SELF-SERVICE IDENTITY: create_workspace did not grant the "
            f"RLS-context user ownership (got {created_actions!r})"
        )
    created_for_other = psql_fn(
        "SELECT count(*) FROM public.workspace_members "
        f"WHERE workspace_id = '{created_workspace_id}'::UUID "
        f"AND user_id = '{_USER_B}'::UUID;"
    ).strip()
    if created_for_other != "0":
        errors.append("SELF-SERVICE IDENTITY: create_workspace granted another user")

    # gdpr.user_info UPDATE is RLS-bound: user A cannot change user B's email.
    _as_app(
        psql_fn,
        _USER_A,
        "UPDATE gdpr.user_info SET email = 'tv_rls_b_hijacked@example.com' "
        f"WHERE user_id = '{_USER_B}'::UUID;",
    )
    user_b_email = psql_fn(
        "SELECT email FROM gdpr.user_info "
        f"WHERE user_id = '{_USER_B}'::UUID;"
    ).strip()
    if user_b_email != "tv_rls_b@example.com":
        errors.append("RLS BEHAVIORAL: user A changed user B's email")

    # Password helpers expose no user-id parameter. Their only target is the
    # current RLS identity, so one user cannot read or overwrite another hash.
    _as_app(
        psql_fn,
        _USER_A,
        "SELECT public.set_current_user_password_hash('hash-for-user-a');",
    )
    _as_app(
        psql_fn,
        _USER_B,
        "SELECT public.set_current_user_password_hash('hash-for-user-b');",
    )
    password_a = _as_app(psql_fn, _USER_A, "SELECT public.get_current_user_password_hash();")
    password_b = _as_app(psql_fn, _USER_B, "SELECT public.get_current_user_password_hash();")
    if password_a != "hash-for-user-a" or password_b != "hash-for-user-b":
        errors.append("SELF-SERVICE IDENTITY: password helper crossed user identities")

    # The scoped DDL helper must reject a user who has no write grant on the
    # target workspace. The block converts the expected SQLSTATE into success.
    index_guard = _as_app(
        psql_fn,
        _USER_A,
        "DO $$ BEGIN "
        "BEGIN "
        "PERFORM public.create_row_data_index("
        f"'{_WS_B}'::UUID, 'idx_rd_222222222222_tvrlstblb_000000000000', "
        "(SELECT table_id FROM public.tables "
        f"WHERE workspace_id = '{_WS_B}'::UUID AND table_name = 'tv_rls_tbl_b'), "
        "'00000000-0000-0000-0000-000000000000', 'text'); "
        "RAISE EXCEPTION 'cross-workspace index creation succeeded'; "
        "EXCEPTION WHEN insufficient_privilege THEN NULL; END; END $$; "
        "SELECT 1;",
    )
    if index_guard != "1":
        errors.append("DDL GUARD: index helper allowed another workspace")

    # SELECT positive: user A can see own workspace tables row
    # (V23: table_schemas merged into tables — config lives here now)
    tbl_a = psql_fn(
        "SELECT table_id FROM public.tables "
        f"WHERE workspace_id = '{_WS_A}'::uuid AND table_name = 'tv_rls_tbl_a';"
    ).strip()
    tbl_b = psql_fn(
        "SELECT table_id FROM public.tables "
        f"WHERE workspace_id = '{_WS_B}'::uuid AND table_name = 'tv_rls_tbl_b';"
    ).strip()
    if not (tbl_a.isdigit() and tbl_b.isdigit()):
        errors.append("RLS SETUP: could not resolve the two table ids")
        return errors

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

    # SELECT isolation: user A cannot see workspace B views. V71 removed the
    # workspace_id column, so isolation is addressed through the table id.
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views WHERE table_id = {tbl_b};",
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
        f"(table_id, config) "
        f"VALUES ({tbl_a},"
        f"""'{{"name":"{_test_name}","type":"kanban"}}'::jsonb);""",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE table_id = {tbl_a} "
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
        f"""WHERE table_id = {tbl_a} """
        f"""  AND config->>'name'='{_test_name}';""",
    )
    type_after = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT 1 FROM public.table_views "
        f"WHERE table_id = {tbl_a} "
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
        f"WHERE table_id = {tbl_a} "
        f"  AND config->>'name'='{_test_name}';",
    )
    count = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.table_views "
        f"WHERE table_id = {tbl_a} "
        f"  AND config->>'name'='{_test_name}';",
    )
    if count != "0":
        errors.append(
            "RLS BEHAVIORAL: user A cannot DELETE in own workspace table_views"
        )

    # V71 rows: the row carries no workspace, so the table id is the whole
    # authority. A member of workspace A must be able to write its own table
    # and be refused on another workspace's table.
    _as_app(
        psql_fn,
        _USER_A,
        f"INSERT INTO public.rows (table_id, row_data) "
        f"VALUES ({tbl_a}, '{{\"probe\":true}}'::jsonb);",
    )
    own_rows = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.rows WHERE table_id = {tbl_a};",
    )
    if not own_rows.isdigit() or int(own_rows) != 1:
        errors.append(
            "RLS BEHAVIORAL: user A cannot INSERT/SELECT rows of own table (V71)"
        )

    foreign_rows = _as_app(
        psql_fn,
        _USER_A,
        f"SELECT COUNT(*) FROM public.rows WHERE table_id = {tbl_b};",
    )
    if foreign_rows.isdigit() and int(foreign_rows) > 0:
        errors.append(
            "RLS BEHAVIORAL: user A can SELECT rows of workspace B (V71)"
        )

    foreign_write = _as_app(
        psql_fn,
        _USER_A,
        "DO $$ BEGIN "
        "BEGIN "
        f"INSERT INTO public.rows (table_id, row_data) "
        f"VALUES ({tbl_b}, '{{}}'::jsonb); "
        "RAISE EXCEPTION 'cross-workspace row accepted'; "
        "EXCEPTION WHEN insufficient_privilege THEN NULL; END; END $$; "
        "SELECT 1;",
    )
    if foreign_write != "1":
        errors.append(
            "RLS BEHAVIORAL: user A can INSERT rows into workspace B (V71)"
        )

    # V52 allows a member to read their own grants, while owners retain the
    # full roster. User A owns workspace A and has no grant on workspace B.
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
