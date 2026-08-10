"""
test_migration_seed.py — Verify the V36 announcement seed after migrations.
"""

_ANNOUNCEMENT_USER_ID = "36baf5e2-b9ae-4ef6-9657-3445a323128c"
_ANNOUNCEMENT_WORKSPACE_ID = "f8bb8500-10f2-4e8c-b0a3-0d5c30778086"


def verify(psql_fn) -> list[str]:
    """Run announcement-seed checks. Returns error strings (empty = pass)."""
    errors: list[str] = []

    # The fixed user, profile, and workspace are the public identity of the
    # announcement data and must remain stable for clients that link to it.
    identity = psql_fn(
        "SELECT u.user_id || '|' || i.email || '|' || i.user_name "
        "|| '|' || w.workspace_id || '|' || w.workspace_name "
        "FROM auth.users AS u "
        "JOIN gdpr.user_info AS i ON i.user_id = u.user_id "
        "JOIN public.workspaces AS w "
        f"  ON w.workspace_id = '{_ANNOUNCEMENT_WORKSPACE_ID}'::uuid "
        f"WHERE u.user_id = '{_ANNOUNCEMENT_USER_ID}'::uuid;"
    ).strip()
    expected_identity = (
        f"{_ANNOUNCEMENT_USER_ID}|announcement@latticecast.local|"
        f"announcement|{_ANNOUNCEMENT_WORKSPACE_ID}|announcement"
    )
    if identity != expected_identity:
        errors.append(
            "WRONG ANNOUNCEMENT IDENTITY: "
            f"expected {expected_identity!r} got {identity!r}"
        )

    # This is deliberately read-only data: the seed identity gets one grant,
    # and that grant is read (not write or owner).
    actions = psql_fn(
        "SELECT string_agg(action, ',' ORDER BY action) "
        "FROM public.workspace_members "
        f"WHERE workspace_id = '{_ANNOUNCEMENT_WORKSPACE_ID}'::uuid "
        f"  AND user_id = '{_ANNOUNCEMENT_USER_ID}'::uuid;"
    ).strip()
    if actions != "read":
        errors.append(
            "WRONG ANNOUNCEMENT ACTIONS: "
            f"expected 'read' got {actions!r}"
        )

    # Blank-template columns are generated first, then V36 adds Type and
    # Time, and V38 replaces Doc/Time with explicit metadata columns. Check the whole
    # generated schema rather than hard-coding UUIDs.
    columns = psql_fn(
        "SELECT string_agg("
        "  (c.column_data ->> 'name') || ':' || (c.column_data ->> 'type'), "
        "  ',' ORDER BY c.ordinality"
        ") "
        "FROM public.tables AS t "
        "CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') "
        "  WITH ORDINALITY AS c(column_data, ordinality) "
        f"WHERE t.workspace_id = '{_ANNOUNCEMENT_WORKSPACE_ID}'::uuid "
        "  AND t.table_id = 'announcement';"
    ).strip()
    expected_columns = (
        "Title:text,Description:text,Type:select,"
        "updated_at:date,updated_by:text,created_at:date,created_by:text"
    )
    if columns != expected_columns:
        errors.append(
            "WRONG ANNOUNCEMENT COLUMNS: "
            f"expected {expected_columns!r} got {columns!r}"
        )

    # create_view() must create a regular table view, not rely only on the
    # frontend's implicit view zero.
    view = psql_fn(
        "SELECT count(*) || '|' || COALESCE(max(config ->> 'name'), '') "
        "|| '|' || COALESCE(max(config ->> 'type'), '') "
        "FROM public.table_views "
        f"WHERE workspace_id = '{_ANNOUNCEMENT_WORKSPACE_ID}'::uuid "
        "  AND table_id = 'announcement';"
    ).strip()
    if view != "1|announcement|table":
        errors.append(
            "WRONG ANNOUNCEMENT VIEW: "
            f"expected '1|announcement|table' got {view!r}"
        )

    return errors
