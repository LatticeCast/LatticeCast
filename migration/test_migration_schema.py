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
    # auth.user_info
    ("auth", "user_info", "user_id", "uuid"),
    ("auth", "user_info", "user_name", "character varying"),
    ("auth", "user_info", "email", "character varying"),
    ("auth", "user_info", "name", "character varying"),
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
    ("public", "tables", "columns", "jsonb"),
    ("public", "tables", "views", "jsonb"),
    ("public", "tables", "created_at", "timestamp"),
    ("public", "tables", "updated_at", "timestamp"),
    # public.rows
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
    ("public", "users", "user_id"),       # moved to auth
    ("public", "user_info", "user_id"),   # moved to auth
    ("auth", "user_info", "display_id"),  # renamed to user_name
    ("public", "workspaces", "display_id"),
    ("public", "workspaces", "name"),
    ("public", "tables", "name"),
    ("public", "tables", "table_name"),
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

    # Check unique constraint on user_info.user_name
    result = psql_fn(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_schema='auth' AND tc.table_name='user_info' "
        "  AND ccu.column_name='user_name' AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: auth.user_info.user_name UNIQUE")

    # Check trigger on rows table
    result = psql_fn(
        "SELECT 1 FROM information_schema.triggers "
        "WHERE event_object_table='rows' AND trigger_name='trg_rows_row_number';"
    )
    if not result:
        errors.append("MISSING TRIGGER: rows.trg_rows_row_number")

    return errors
