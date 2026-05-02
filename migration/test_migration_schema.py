"""
test_migration_schema.py — Verify table/column structure after migrations.
Called by test_migrations.py (not standalone).
"""

# Expected columns: (schema, table, column, data_type_fragment)
EXPECTED_COLUMNS: list[tuple[str, str, str, str]] = [
    # auth.users
    ("auth", "users", "user_id", "uuid"),
    ("auth", "users", "role", "character varying"),
    ("auth", "users", "created_at", "timestamp"),
    ("auth", "users", "updated_at", "timestamp"),
    # auth.gdpr — PII (login_mgr only)
    ("auth", "gdpr", "user_id", "uuid"),
    ("auth", "gdpr", "email", "character varying"),
    ("auth", "gdpr", "legal_name", "character varying"),
    # public.user_info — public handle only
    ("public", "user_info", "user_id", "uuid"),
    ("public", "user_info", "user_name", "character varying"),
    # public.workspaces
    ("public", "workspaces", "workspace_id", "uuid"),
    ("public", "workspaces", "workspace_name", "character varying"),
    ("public", "workspaces", "created_at", "timestamp"),
    ("public", "workspaces", "updated_at", "timestamp"),
    # public.workspace_members
    ("public", "workspace_members", "workspace_id", "uuid"),
    ("public", "workspace_members", "user_id", "uuid"),
    ("public", "workspace_members", "role", "character varying"),
    # public.tables (V34: identity only — columns moved to __schema__ row)
    ("public", "tables", "workspace_id", "uuid"),
    ("public", "tables", "table_id", "character varying"),
    ("public", "tables", "created_at", "timestamp"),
    ("public", "tables", "updated_at", "timestamp"),
    # public.table_views (V34 simplified shape)
    ("public", "table_views", "workspace_id", "uuid"),
    ("public", "table_views", "table_id", "character varying"),
    ("public", "table_views", "name", "character varying"),
    ("public", "table_views", "type", "character varying"),
    ("public", "table_views", "config", "jsonb"),
    ("public", "table_views", "created_by", "uuid"),
    ("public", "table_views", "updated_by", "uuid"),
    ("public", "table_views", "created_at", "timestamp"),
    ("public", "table_views", "updated_at", "timestamp"),
    # public.rows
    ("public", "rows", "workspace_id", "uuid"),
    ("public", "rows", "table_id", "character varying"),
    ("public", "rows", "row_number", "bigint"),
    ("public", "rows", "row_data", "jsonb"),
    ("public", "rows", "created_by", "uuid"),
    ("public", "rows", "updated_by", "uuid"),
    ("public", "rows", "created_at", "timestamp"),
    ("public", "rows", "updated_at", "timestamp"),
]

# Columns that must NOT exist
FORBIDDEN_COLUMNS: list[tuple[str, str, str]] = [
    ("public", "users", "user_id"),          # moved to auth
    ("auth", "user_info", "user_id"),        # stays in public
    ("auth", "user_info", "display_id"),     # renamed to user_name
    ("public", "user_info", "email"),        # moved to auth.gdpr
    ("public", "user_info", "name"),         # removed (legal_name in auth.gdpr)
    ("public", "user_info", "display_name"), # removed — user_name is the only handle
    ("public", "workspaces", "display_id"),
    ("public", "workspaces", "name"),
    ("public", "tables", "name"),
    ("public", "tables", "table_name"),
    ("public", "tables", "views"),
    ("public", "tables", "columns"),                  # V34: moved to __schema__ row
    ("public", "table_views", "view_number"),         # V34: dropped
    ("public", "table_views", "is_default"),          # V34: dropped
    ("public", "table_views", "next_view_id"),        # V34: dropped
]


def verify(psql_fn) -> list[str]:
    """Run schema checks. Returns list of error strings (empty = pass)."""
    errors: list[str] = []

    # Check schemas exist
    schemas_raw = psql_fn(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name IN ('public', 'auth', 'private');"
    )
    schemas = set(schemas_raw.splitlines()) if schemas_raw else set()
    for s in ("public", "auth"):
        if s not in schemas:
            errors.append(f"MISSING SCHEMA: {s}")

    # Check expected columns
    for schema, table, column, dtype_fragment in EXPECTED_COLUMNS:
        result = psql_fn(
            f"SELECT data_type FROM information_schema.columns "
            f"WHERE table_schema='{schema}' AND table_name='{table}' AND column_name='{column}';"
        )
        if not result:
            errors.append(f"MISSING COLUMN: {schema}.{table}.{column}")
        elif dtype_fragment not in result:
            errors.append(f"WRONG TYPE: {schema}.{table}.{column} expected '{dtype_fragment}' got '{result}'")

    # Check forbidden columns
    for schema, table, column in FORBIDDEN_COLUMNS:
        result = psql_fn(
            f"SELECT 1 FROM information_schema.columns "
            f"WHERE table_schema='{schema}' AND table_name='{table}' AND column_name='{column}';"
        )
        if result:
            errors.append(f"FORBIDDEN COLUMN still present: {schema}.{table}.{column}")

    # Check unique constraint on public.user_info.user_name
    result = psql_fn(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_schema='public' AND tc.table_name='user_info' "
        "  AND ccu.column_name='user_name' AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: public.user_info.user_name UNIQUE")

    # Check unique constraint on auth.gdpr.email
    result = psql_fn(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_schema='auth' AND tc.table_name='gdpr' "
        "  AND ccu.column_name='email' AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: auth.gdpr.email UNIQUE")

    # Check trigger on rows table
    result = psql_fn(
        "SELECT 1 FROM information_schema.triggers "
        "WHERE event_object_table='rows' AND trigger_name='trg_rows_row_number';"
    )
    if not result:
        errors.append("MISSING TRIGGER: rows.trg_rows_row_number")

    # V34/V35: Triggers on table_views and tables
    # (V35 dropped trg_table_views_prevent_schema_delete — API layer enforces it)
    for trg_name, tbl in [
        ("trg_tables_create_schema_and_order", "tables"),
    ]:
        result = psql_fn(
            f"SELECT 1 FROM information_schema.triggers "
            f"WHERE event_object_table='{tbl}' AND trigger_name='{trg_name}';"
        )
        if not result:
            errors.append(f"MISSING TRIGGER: {tbl}.{trg_name}")

    # V33's partial unique index is dropped in V34
    result = psql_fn(
        "SELECT 1 FROM pg_indexes "
        "WHERE schemaname='public' AND tablename='table_views' "
        "  AND indexname='table_views_one_default';"
    )
    if result:
        errors.append(
            "FORBIDDEN INDEX still present: "
            "public.table_views.table_views_one_default (V34 drop)"
        )

    # RLS policy on table_views still in place
    result = psql_fn(
        "SELECT 1 FROM pg_policies "
        "WHERE schemaname='public' AND tablename='table_views' "
        "  AND policyname='table_views_workspace_member';"
    )
    if not result:
        errors.append(
            "MISSING RLS POLICY: public.table_views.table_views_workspace_member"
        )

    # V34: PK is (workspace_id, table_id, name)
    result = psql_fn(
        "SELECT string_agg(kcu.column_name, ',' "
        "  ORDER BY kcu.ordinal_position) "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "  AND tc.table_schema = kcu.table_schema "
        "WHERE tc.table_schema='public' "
        "  AND tc.table_name='table_views' "
        "  AND tc.constraint_type='PRIMARY KEY';"
    )
    expected_pk = "workspace_id,table_id,name"
    if result.strip() != expected_pk:
        errors.append(
            f"WRONG PK: table_views expected '{expected_pk}' "
            f"got '{result.strip()}'"
        )

    # V33: FK to public.tables ON DELETE CASCADE
    result = psql_fn(
        "SELECT 1 FROM pg_constraint c "
        "JOIN pg_class t ON c.conrelid = t.oid "
        "JOIN pg_namespace n ON t.relnamespace = n.oid "
        "WHERE n.nspname='public' AND t.relname='table_views' "
        "  AND c.conname='table_views_table_fkey' "
        "  AND c.confdeltype='c';"
    )
    if not result:
        errors.append(
            "MISSING/WRONG FK: table_views_table_fkey "
            "(expected ON DELETE CASCADE)"
        )

    # V34: self-FK next_view_id is dropped — no longer present
    result = psql_fn(
        "SELECT 1 FROM pg_constraint "
        "WHERE conname='table_views_next_fkey';"
    )
    if result:
        errors.append("FORBIDDEN FK still present: table_views_next_fkey")

    # V34/V35 trigger functions
    for fn_name in (
        "trg_create_schema_and_order_fn",
    ):
        result = psql_fn(
            f"SELECT 1 FROM pg_proc WHERE proname='{fn_name}';"
        )
        if not result:
            errors.append(f"MISSING TRIGGER FUNCTION: {fn_name}")

    return errors
