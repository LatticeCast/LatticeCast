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
    # public.workspace_members (V33: role → multi-row action grant)
    ("public", "workspace_members", "workspace_id", "uuid"),
    ("public", "workspace_members", "user_id", "uuid"),
    ("public", "workspace_members", "action", "character varying"),
    # public.tables (V23: merged table_schemas into tables)
    ("public", "tables", "workspace_id", "uuid"),
    ("public", "tables", "table_id", "character varying"),
    ("public", "tables", "config", "jsonb"),
    ("public", "tables", "created_by", "uuid"),
    ("public", "tables", "updated_by", "uuid"),
    ("public", "tables", "created_at", "timestamp"),
    ("public", "tables", "updated_at", "timestamp"),
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

# Columns that must NOT exist after the squash.
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
    ("public", "tables", "columns"),         # in tables.config JSONB now
    ("public", "table_views", "name"),       # in config jsonb now
    ("public", "table_views", "type"),       # in config jsonb now
    ("public", "table_views", "is_default"), # default_view in tables.config
    ("public", "workspace_members", "role"), # V33: replaced by action
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

    # V23 dropped trg_tables_create_table_schema (table_schemas merged
    # into tables — config column has a DEFAULT now).

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

    # RLS policy on table_views still in place (V33: read/write split)
    result = psql_fn(
        "SELECT 1 FROM pg_policies "
        "WHERE schemaname='public' AND tablename='table_views' "
        "  AND policyname='table_views_read';"
    )
    if not result:
        errors.append(
            "MISSING RLS POLICY: public.table_views.table_views_read"
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

    # V26: CHECK constraint on table_views.config->>'type'
    result = psql_fn(
        "SELECT 1 FROM pg_constraint "
        "WHERE conrelid = 'public.table_views'::regclass "
        "  AND conname = 'table_views_valid_type' "
        "  AND contype = 'c';"
    )
    if not result:
        errors.append(
            "MISSING CHECK: table_views_valid_type (V26)"
        )

    # V35: path-facing workspace/table names cannot contain dots. Both
    # constraints are validated, so they cover existing and future rows.
    for relation, constraint in [
        ("public.workspaces", "workspaces_workspace_name_no_dot"),
        ("public.tables", "tables_table_id_no_dot"),
    ]:
        result = psql_fn(
            "SELECT convalidated FROM pg_constraint "
            f"WHERE conrelid = '{relation}'::regclass "
            f"  AND conname = '{constraint}' "
            "  AND contype = 'c';"
        ).strip()
        if result != "t":
            errors.append(
                f"MISSING/UNVALIDATED CHECK: {constraint} (V35)"
            )

    # V27: _seed_workflow function exists
    result = psql_fn(
        "SELECT 1 FROM pg_proc "
        "WHERE proname='_seed_workflow';"
    )
    if not result:
        errors.append(
            "MISSING FUNCTION: _seed_workflow (V27)"
        )

    # V27: create_table_from_template handles 'workflow' kind
    result = psql_fn(
        "SELECT pg_get_functiondef(oid) "
        "FROM pg_proc "
        "WHERE proname='create_table_from_template';"
    )
    if result and 'workflow' not in result:
        errors.append(
            "MISSING CASE: create_table_from_template "
            "does not handle 'workflow' (V27)"
        )

    # V18's helper remains for migration compatibility, but V49's temporal
    # indexes must no longer use it: JSONB date/datetime cells are epoch-ms.
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

    result = psql_fn(
        "SELECT count(*) FROM pg_indexes "
        "WHERE schemaname='public' "
        "  AND indexdef LIKE '%immutable_iso_to_ts(%';"
    ).strip()
    if result != "0":
        errors.append(
            "RETIRED TEMPORAL INDEX: immutable_iso_to_ts still backs "
            f"{result} public index(es) (V49)"
        )

    # V48/V49: JSONB temporal cells are UTC epoch-millisecond numbers and a
    # rows trigger enforces the representation for every write path.
    for function_name, signature in [
        ("to_canonical_epoch_ms", "jsonb, text"),
        ("_normalize_row_data_timestamps", "jsonb, jsonb"),
    ]:
        result = psql_fn(
            "SELECT to_regprocedure("
            f"'public.{function_name}({signature})'"
            ");"
        ).strip()
        if not result:
            errors.append(f"MISSING TEMPORAL FUNCTION: {function_name} (V48/V49)")

    result = psql_fn(
        "SELECT 1 FROM information_schema.triggers "
        "WHERE event_object_schema='public' "
        "  AND event_object_table='rows' "
        "  AND trigger_name='trg_rows_canonical_ts';"
    )
    if not result:
        errors.append("MISSING TRIGGER: rows.trg_rows_canonical_ts (V49)")

    result = psql_fn(
        "SELECT public.to_canonical_epoch_ms("
        "'\"2025-05-15\"'::jsonb, 'date')::text;"
    ).strip()
    if result != "1747267200000":
        errors.append(
            "WRONG EPOCH NORMALIZATION: expected 1747267200000 for "
            f"2025-05-15 UTC, got {result!r}"
        )

    # V50: ordinary RDS datetime columns remain timestamp-without-zone but
    # their defaults state the UTC+0 convention explicitly.
    result = psql_fn("SHOW timezone;").strip()
    if result.upper() != "UTC":
        errors.append(f"WRONG DATABASE TIMEZONE: expected UTC got {result!r} (V50)")

    result = psql_fn(
        "SELECT pg_get_expr(adbin, adrelid) "
        "FROM pg_attrdef "
        "WHERE adrelid='public.rows'::regclass "
        "  AND adnum=(SELECT attnum FROM pg_attribute "
        "             WHERE attrelid='public.rows'::regclass "
        "               AND attname='created_at' AND NOT attisdropped);"
    ).strip()
    if "AT TIME ZONE 'UTC'" not in result:
        errors.append("WRONG DEFAULT: public.rows.created_at is not explicit UTC (V50)")

    # V51: per-table counter and allocator replace MAX(row_id)+1.
    result = psql_fn(
        "SELECT to_regclass('private.table_row_counters');"
    ).strip()
    if result != "private.table_row_counters":
        errors.append("MISSING TABLE: private.table_row_counters (V51)")

    result = psql_fn(
        "SELECT prosecdef FROM pg_proc "
        "WHERE oid='public.trg_set_row_id_fn()'::regprocedure;"
    ).strip()
    if result != "t":
        errors.append("ROW ID ALLOCATOR IS NOT SECURITY DEFINER (V51)")

    # V52 uses the caller's allowed-workspace set, not a row-correlated
    # check_workspace_permission invocation inside the policy.
    result = psql_fn(
        "SELECT to_regprocedure('public.current_user_workspaces(character varying)');"
    ).strip()
    if not result:
        errors.append("MISSING FUNCTION: current_user_workspaces (V52)")

    result = psql_fn(
        "SELECT qual FROM pg_policies "
        "WHERE schemaname='public' AND tablename='rows' "
        "  AND policyname='rows_read';"
    ).strip()
    if "current_user_workspaces" not in result:
        errors.append("ROWS RLS IS NOT SET-BASED (V52)")

    # V33: workspace_members PK is (workspace_id, user_id, action) —
    # multiple rows per member, one per granted action.
    result = psql_fn(
        "SELECT string_agg(kcu.column_name, ',' "
        "  ORDER BY kcu.ordinal_position) "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "  AND tc.table_schema = kcu.table_schema "
        "WHERE tc.table_schema='public' "
        "  AND tc.table_name='workspace_members' "
        "  AND tc.constraint_type='PRIMARY KEY';"
    )
    expected_pk = "workspace_id,user_id,action"
    if result.strip() != expected_pk:
        errors.append(
            f"WRONG PK: workspace_members expected '{expected_pk}' "
            f"got '{result.strip()}'"
        )

    # V33: action CHECK constraint restricts to read/write/owner.
    result = psql_fn(
        "SELECT 1 FROM pg_constraint "
        "WHERE conrelid = 'public.workspace_members'::regclass "
        "  AND conname = 'workspace_members_action_check' "
        "  AND contype = 'c';"
    )
    if not result:
        errors.append(
            "MISSING CHECK: workspace_members_action_check (V33)"
        )

    # V33: check_workspace_permission replaces check_workspace_member.
    result = psql_fn(
        "SELECT 1 FROM pg_proc WHERE proname='check_workspace_permission';"
    )
    if not result:
        errors.append("MISSING FUNCTION: check_workspace_permission (V33)")

    result = psql_fn(
        "SELECT 1 FROM pg_proc WHERE proname='check_workspace_member';"
    )
    if result:
        errors.append(
            "FORBIDDEN FUNCTION still present: check_workspace_member (V33 drop)"
        )

    # V45: PATCH and PUT row semantics are separate PG functions. The old
    # ambiguous update_row_data function must not remain callable.
    for function_name in ("patch_row_data", "put_row_data"):
        result = psql_fn(
            "SELECT 1 FROM pg_proc "
            f"WHERE proname='{function_name}';"
        )
        if not result:
            errors.append(f"MISSING FUNCTION: {function_name} (V45)")

    result = psql_fn(
        "SELECT 1 FROM pg_proc WHERE proname='update_row_data';"
    )
    if result:
        errors.append("FORBIDDEN FUNCTION still present: update_row_data (V45 drop)")

    # V45 replaces V44's SECURITY DEFINER blob mutation as well. Row mutation
    # functions must execute as app so rows RLS policies cannot be bypassed.
    for function_name in ("patch_row_data", "put_row_data", "update_blob_cell"):
        result = psql_fn(
            "SELECT prosecdef FROM pg_proc "
            f"WHERE proname='{function_name}';"
        ).strip()
        if result != "f":
            errors.append(f"RLS-BYPASS FUNCTION: {function_name} (V45)")

    # Both public V45 functions invoke this SECURITY INVOKER helper.
    result = psql_fn(
        "SELECT has_function_privilege("
        "'app', 'public._validate_row_data_mutation(uuid, varchar, jsonb)', 'EXECUTE'"
        ");"
    ).strip()
    if result != "t":
        errors.append("MISSING EXECUTE: app on _validate_row_data_mutation (V45)")

    # V46 removes caller-controlled identities from self-service functions.
    for function_name, signature in [
        ("create_workspace", "character varying"),
        ("get_user_sidebar", ""),
        ("get_current_user_password_hash", ""),
        ("set_current_user_password_hash", "character varying"),
    ]:
        result = psql_fn(
            "SELECT has_function_privilege("
            f"'app', 'public.{function_name}({signature})', 'EXECUTE'"
            ");"
        ).strip()
        if result != "t":
            errors.append(f"MISSING EXECUTE: app on {function_name} (V46)")

    for old_function, signature in [
        ("create_workspace", "character varying, uuid"),
        ("get_user_sidebar", "uuid"),
    ]:
        result = psql_fn(
            "SELECT to_regprocedure("
            f"'public.{old_function}({signature})'"
            ");"
        ).strip()
        if result:
            errors.append(f"FORBIDDEN CALLER IDENTITY FUNCTION: {old_function} (V46)")

    # _build_rd_idx_name(text, text) is deliberately NOT in this list. V49
    # dropped it as dead surface and asserted here that it must not come back,
    # but it is live: the current drop_row_data_index(uuid, text, text, text)
    # drops TWO index names for a column -- the workspace-scoped one it now
    # creates, and the unscoped one any database migrated before V47 still
    # carries -- and it needs this two-argument helper to rebuild that older
    # name. Without it, deleting any indexed column fails outright:
    #
    #     ERROR: function public._build_rd_idx_name(text, text) does not exist
    #
    # V49's "nothing reaches them" check used a query returning only the FIRST
    # match per function body, which hid that second call; regexp_matches with
    # the 'g' flag shows both. V55 restored the function, so this assertion
    # would now fail the suite on a correct schema.
    for old_function, signature in [
        ("create_row_data_index", "text, text, text, text"),
        ("drop_row_data_index", "text"),
    ]:
        result = psql_fn(
            "SELECT to_regprocedure("
            f"'public.{old_function}({signature})'"
            ");"
        ).strip()
        if result:
            errors.append(f"FORBIDDEN LEGACY DDL FUNCTION: {old_function} (V49)")

    # The legacy helper must exist, and must NOT be reachable by app: its only
    # caller is a SECURITY DEFINER function that runs as its owner (V55).
    result = psql_fn(
        "SELECT to_regprocedure('public._build_rd_idx_name(text, text)');"
    ).strip()
    if not result:
        errors.append("MISSING LEGACY DDL HELPER: _build_rd_idx_name(text, text) (V55)")
    result = psql_fn(
        "SELECT has_function_privilege("
        "'app', 'public._build_rd_idx_name(text, text)', 'EXECUTE'"
        ");"
    ).strip()
    if result == "t":
        errors.append("UNEXPECTED EXECUTE: app on legacy index-name helper (V55)")

    result = psql_fn(
        "SELECT has_function_privilege("
        "'app', 'public._build_rd_idx_name(uuid, text, text)', 'EXECUTE'"
        ");"
    ).strip()
    if result != "t":
        errors.append("MISSING EXECUTE: app on scoped index-name helper (V47)")

    # V53 removes the scalar permission check from app sessions; RLS owns
    # authorization and SECURITY DEFINER DDL helpers retain owner access.
    result = psql_fn(
        "SELECT has_function_privilege("
        "'app', 'public.check_workspace_permission(uuid, uuid, character varying)', "
        "'EXECUTE'"
        ");"
    ).strip()
    if result != "f":
        errors.append("APP CAN EXECUTE SCALAR PERMISSION CHECK (V53)")

    # V33: grant_workspace_action does the atomic multi-row grant/revoke.
    result = psql_fn(
        "SELECT 1 FROM pg_proc WHERE proname='grant_workspace_action';"
    )
    if not result:
        errors.append("MISSING FUNCTION: grant_workspace_action (V33)")

    # V39: the table trigger must reject names that collide after the
    # case-insensitive, whitespace-trimming normalization. Keep this inside
    # the migration verifier so it exercises the installed trigger, not only
    # the helper function's implementation.
    result = psql_fn(
        "CREATE TEMP TABLE column_name_validation_result ("
        "  was_rejected BOOLEAN NOT NULL"
        "); "
        "INSERT INTO column_name_validation_result VALUES (FALSE); "
        "INSERT INTO public.workspaces (workspace_id, workspace_name) "
        "VALUES ('39000000-0000-0000-0000-000000000001'::uuid, "
        "'column_name_validation') "
        "ON CONFLICT (workspace_id) DO NOTHING; "
        "DO $$ "
        "BEGIN "
        "  INSERT INTO public.tables (workspace_id, table_id, config) "
        "  VALUES ("
        "    '39000000-0000-0000-0000-000000000001'::uuid, "
        "    'duplicate_column_names', "
        "    '{\"columns\":[{\"column_id\":\"first\",\"name\":\"Status\"},"
        "{\"column_id\":\"second\",\"name\":\" status \"}]}'::jsonb"
        "  ); "
        "EXCEPTION WHEN unique_violation THEN "
        "  UPDATE column_name_validation_result SET was_rejected = TRUE; "
        "END; "
        "$$; "
        "SELECT was_rejected FROM column_name_validation_result;"
    )
    rejected = result.splitlines()[-1].strip() if result else ""
    if rejected != "t":
        errors.append(
            "COLUMN NAME VALIDATION: duplicate normalized names were accepted"
        )

    return errors
