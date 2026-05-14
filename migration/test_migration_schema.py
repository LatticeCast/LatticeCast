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
    # gdpr.user_info — PII that can remove easily
    ("gdpr", "user_info", "user_id", "uuid"),
    ("gdpr", "user_info", "email", "character varying"),
    ("gdpr", "user_info", "user_name", "character varying"),
    ("gdpr", "user_info", "config", "jsonb"),
    # public.workspaces
    ("public", "workspaces", "workspace_id", "uuid"),
    ("public", "workspaces", "workspace_name", "character varying"),
    ("public", "workspaces", "created_at", "timestamp"),
    ("public", "workspaces", "updated_at", "timestamp"),
    # public.workspace_members
    ("public", "workspace_members", "workspace_id", "uuid"),
    ("public", "workspace_members", "user_id", "uuid"),
    ("public", "workspace_members", "role", "character varying"),
    # public.tables
    ("public", "tables", "workspace_id", "uuid"),
    ("public", "tables", "table_id", "character varying"),
    ("public", "tables", "created_at", "timestamp"),
    ("public", "tables", "updated_at", "timestamp"),
    # public.table_schemas
    ("public", "table_schemas", "workspace_id", "uuid"),
    ("public", "table_schemas", "table_id", "character varying"),
    ("public", "table_schemas", "config", "jsonb"),
    ("public", "table_schemas", "created_by", "uuid"),
    ("public", "table_schemas", "updated_by", "uuid"),
    ("public", "table_schemas", "created_at", "timestamp"),
    ("public", "table_schemas", "updated_at", "timestamp"),
    # public.rows
    ("public", "rows", "workspace_id", "uuid"),
    ("public", "rows", "table_id", "character varying"), 
    ("public", "rows", "row_id", "bigint"),
    ("public", "rows", "row_data", "jsonb"),
    ("public", "rows", "created_by", "uuid"),
    ("public", "rows", "updated_by", "uuid"),
    ("public", "rows", "created_at", "timestamp"),
    ("public", "rows", "updated_at", "timestamp"),
    # public.table_views
    ("public", "table_views", "workspace_id", "uuid"),
    ("public", "table_views", "table_id", "character varying"),
    ("public", "table_views", "view_id", "bigint"),
    ("public", "table_views", "config", "jsonb"),
    ("public", "table_views", "created_by", "uuid"),
    ("public", "table_views", "updated_by", "uuid"),
    ("public", "table_views", "created_at", "timestamp"),
    ("public", "table_views", "updated_at", "timestamp"),
]

# Columns that must NOT exist after the v40 squash.
FORBIDDEN_COLUMNS: list[tuple[str, str, str]] = [
    ("public", "users", "user_id"),          # moved to auth.users
    ("public", "user_info", "user_id"),      # moved to gdpr.user_info
    ("public", "user_info", "user_name"),    # moved to gdpr.user_info
    ("auth", "gdpr", "user_id"),             # merged into gdpr.user_info
    ("auth", "gdpr", "email"),               # merged into gdpr.user_info
    ("auth", "gdpr", "legal_name"),          # dropped — not in v40 schema
    ("public", "workspaces", "display_id"),
    ("public", "tables", "name"),
    ("public", "tables", "table_name"),
    ("public", "tables", "columns"),         # in table_schemas.config now
    ("public", "table_views", "name"),       # in config jsonb now
    ("public", "table_views", "type"),       # in config jsonb now
    ("public", "table_views", "is_default"), # default_view in table_schemas.config
]


def verify(psql_fn) -> list[str]:
    """Run schema checks. Returns list of error strings (empty = pass)."""
    errors: list[str] = []

    # Check schemas exist
    schemas_raw = psql_fn(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name IN ('public', 'auth', 'gdpr', 'private');"
    )
    schemas = set(schemas_raw.splitlines()) if schemas_raw else set()
    for s in ("public", "auth", "gdpr", "private"):
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

    # Check unique constraint on gdpr.user_info.user_name
    result = psql_fn(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_schema='gdpr' AND tc.table_name='user_info' "
        "  AND ccu.column_name='user_name' AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: gdpr.user_info.user_name UNIQUE")

    # Check unique constraint on gdpr.user_info.email
    result = psql_fn(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_schema='gdpr' AND tc.table_name='user_info' "
        "  AND ccu.column_name='email' AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: gdpr.user_info.email UNIQUE")

    # Check trigger on rows table
    result = psql_fn(
        "SELECT 1 FROM information_schema.triggers "
        "WHERE event_object_table='rows' AND trigger_name='trg_rows_row_id';"
    )
    if not result:
        errors.append("MISSING TRIGGER: rows.trg_rows_row_id")

    # V43 replaces V34's schema+order trigger with one that auto-creates
    # the table_schemas SSOT row on table insert.
    for trg_name, tbl in [
        ("trg_tables_create_table_schema", "tables"),
    ]:
        result = psql_fn(
            f"SELECT 1 FROM information_schema.triggers "
            f"WHERE event_object_table='{tbl}' AND trigger_name='{trg_name}';"
        )
        if not result:
            errors.append(f"MISSING TRIGGER: {tbl}.{trg_name}")

    # V41 drops V37's partial unique index (default_view moved into config).
    result = psql_fn(
        "SELECT 1 FROM pg_indexes "
        "WHERE schemaname='public' AND tablename='table_views' "
        "  AND indexname='table_views_one_default';"
    )
    if result:
        errors.append(
            "FORBIDDEN INDEX still present: "
            "public.table_views.table_views_one_default (V41 drop)"
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

    # v40: PK is (workspace_id, table_id, view_id BIGINT)
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
    expected_pk = "workspace_id,table_id,view_id"
    if result.strip() != expected_pk:
        errors.append(
            f"WRONG PK: table_views expected '{expected_pk}' "
            f"got '{result.strip()}'"
        )

    # FK from public.table_views (workspace_id, table_id) → public.tables
    # with ON DELETE CASCADE. The constraint name is auto-generated by PG
    # (no explicit CONSTRAINT clause in V9), so match by referenced table
    # + delete-action instead.
    result = psql_fn(
        "SELECT 1 FROM pg_constraint c "
        "JOIN pg_class t ON c.conrelid = t.oid "
        "JOIN pg_namespace n ON t.relnamespace = n.oid "
        "JOIN pg_class rt ON c.confrelid = rt.oid "
        "WHERE n.nspname='public' AND t.relname='table_views' "
        "  AND rt.relname='tables' AND c.contype='f' "
        "  AND c.confdeltype='c';"
    )
    if not result:
        errors.append(
            "MISSING/WRONG FK: table_views → tables "
            "(expected ON DELETE CASCADE)"
        )

    # V43 trigger function (replaces V34's trg_create_schema_and_order_fn).
    for fn_name in (
        "trg_create_table_schema_fn",
    ):
        result = psql_fn(
            f"SELECT 1 FROM pg_proc WHERE proname='{fn_name}';"
        )
        if not result:
            errors.append(f"MISSING TRIGGER FUNCTION: {fn_name}")

    # V18: immutable_iso_to_ts must exist so create_row_data_index() can
    # build btree indexes on date columns (::NUMERIC cast fails on ISO strings).
    result = psql_fn(
        "SELECT 1 FROM pg_proc WHERE proname='immutable_iso_to_ts';"
    )
    if not result:
        errors.append("MISSING FUNCTION: immutable_iso_to_ts (V18)")

    # V18: verify immutable_iso_to_ts correctly converts an ISO date string.
    result = psql_fn(
        "SELECT immutable_iso_to_ts('2025-05-15')::DATE::TEXT;"
    )
    if result.strip() != "2025-05-15":
        errors.append(
            f"WRONG RESULT: immutable_iso_to_ts('2025-05-15') "
            f"expected '2025-05-15' got '{result.strip()}'"
        )

    return errors
