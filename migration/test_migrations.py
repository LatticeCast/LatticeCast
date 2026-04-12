#!/usr/bin/env python3
"""
Migration test script — spins up a temporary PostgreSQL container,
runs all migration/*.sql files in sorted order, verifies the final
schema matches expectations, then tears down.

Usage:
    python migration/test_migrations.py

Exit codes:
    0 — all migrations applied and schema verified
    1 — migration error or schema mismatch
"""

import subprocess
import sys
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CONTAINER_NAME = "latticecast-migration-test"
PG_IMAGE = "postgres:18"
PG_USER = "testuser"
PG_PASSWORD = "testpass"
PG_DB = "testdb"
PG_PORT = 15433  # unlikely to clash with a running dev DB

MIGRATION_DIR = Path(__file__).parent

# 0021_tables_reorder was applied in production AFTER 0018 (when table_id was still UUID
# and table_name existed), but BEFORE 0019 converted table_id to VARCHAR and dropped
# table_name.  Running it after 0019 would fail (SELECT table_name on a non-existent column).
# Override its sort key so it is applied between 0018 and 0019.
MIGRATION_SORT_OVERRIDES: dict[str, str] = {
    "0021_tables_reorder.sql": "0018.5_tables_reorder.sql",
}


def _migration_sort_key(path: Path) -> str:
    return MIGRATION_SORT_OVERRIDES.get(path.name, path.name)


# ── Expected final schema ─────────────────────────────────────────────────────
# Each entry: (table_name, column_name, data_type_fragment)
# data_type_fragment is a substring match against pg information_schema data_type.

EXPECTED_COLUMNS: list[tuple[str, str, str]] = [
    # users
    ("users", "user_id", "uuid"),
    ("users", "role", "character varying"),
    ("users", "created_at", "timestamp"),
    ("users", "updated_at", "timestamp"),
    # user_info
    ("user_info", "user_id", "uuid"),
    ("user_info", "user_name", "character varying"),
    ("user_info", "email", "character varying"),
    ("user_info", "name", "character varying"),
    # workspaces
    ("workspaces", "workspace_id", "uuid"),
    ("workspaces", "workspace_name", "character varying"),
    ("workspaces", "created_at", "timestamp"),
    ("workspaces", "updated_at", "timestamp"),
    # workspace_members
    ("workspace_members", "workspace_id", "uuid"),
    ("workspace_members", "user_id", "uuid"),
    ("workspace_members", "role", "character varying"),
    # tables
    ("tables", "workspace_id", "uuid"),
    ("tables", "table_id", "character varying"),  # string PK — table_id IS the name (0019)
    ("tables", "columns", "jsonb"),
    ("tables", "views", "jsonb"),
    ("tables", "created_at", "timestamp"),
    ("tables", "updated_at", "timestamp"),
    # rows
    ("rows", "table_id", "character varying"),  # string FK matching tables.table_id (0019)
    ("rows", "row_number", "bigint"),
    ("rows", "row_data", "jsonb"),
    ("rows", "created_by", "uuid"),
    ("rows", "updated_by", "uuid"),
    ("rows", "created_at", "timestamp"),
    ("rows", "updated_at", "timestamp"),
]

EXPECTED_TABLES = {t for t, _, _ in EXPECTED_COLUMNS}

# Columns that must NOT exist (renamed/dropped in migrations)
FORBIDDEN_COLUMNS: list[tuple[str, str]] = [
    ("users", "email"),           # moved to user_info
    ("user_info", "display_id"),  # renamed to user_name in 0019
    ("workspaces", "display_id"), # merged into workspace_name in 0017
    ("workspaces", "name"),       # merged into workspace_name in 0017
    ("tables", "name"),           # renamed to table_name in 0018
    ("tables", "table_name"),     # removed in 0019 (table_id IS the name now)
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def psql(sql: str) -> str:
    """Run SQL against the temp container and return stdout."""
    result = run(
        [
            "docker", "exec", CONTAINER_NAME,
            "psql", f"--username={PG_USER}", f"--dbname={PG_DB}",
            "--no-password", "--tuples-only", "--no-align",
            "--command", sql,
        ],
        capture=True,
    )
    return result.stdout.strip()


def psql_file(path: Path) -> None:
    """Execute a SQL file inside the container, fail fast on error."""
    run(
        [
            "docker", "exec", "--interactive", CONTAINER_NAME,
            "psql", f"--username={PG_USER}", f"--dbname={PG_DB}",
            "--no-password", "--set", "ON_ERROR_STOP=1",
            "--file", f"/migration/{path.name}",
        ]
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_container() -> None:
    print(f"[start] Starting temporary PostgreSQL container ({PG_IMAGE})…")
    run([
        "docker", "run", "--rm", "--detach",
        "--name", CONTAINER_NAME,
        "--publish", f"127.0.0.1:{PG_PORT}:5432",
        "--env", f"POSTGRES_USER={PG_USER}",
        "--env", f"POSTGRES_PASSWORD={PG_PASSWORD}",
        "--env", f"POSTGRES_DB={PG_DB}",
        "--volume", f"{MIGRATION_DIR.resolve()}:/migration:ro",
        PG_IMAGE,
    ])


def wait_for_pg(timeout: int = 30) -> None:
    print("[wait]  Waiting for PostgreSQL to be ready…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run(
            ["docker", "exec", CONTAINER_NAME,
             "pg_isready", "-U", PG_USER, "-d", PG_DB],
            check=False, capture=True,
        )
        if result.returncode == 0:
            print("[wait]  PostgreSQL is ready.")
            return
        time.sleep(1)
    raise RuntimeError(f"PostgreSQL did not become ready within {timeout}s")


def stop_container() -> None:
    print("[stop]  Stopping container…")
    run(["docker", "stop", CONTAINER_NAME], check=False, capture=True)


# ── Migration runner ──────────────────────────────────────────────────────────

def run_migrations() -> None:
    sql_files = sorted(MIGRATION_DIR.glob("*.sql"), key=_migration_sort_key)
    if not sql_files:
        raise RuntimeError(f"No *.sql files found in {MIGRATION_DIR}")

    print(f"[migrate] Applying {len(sql_files)} migration file(s)…")
    for sql_file in sql_files:
        print(f"  → {sql_file.name}")
        psql_file(sql_file)

    print("[migrate] All migrations applied successfully.")


# ── Schema verification ───────────────────────────────────────────────────────

def verify_schema() -> None:
    print("[verify] Checking schema…")
    errors: list[str] = []

    # 1. Check all expected tables exist
    existing_tables_raw = psql(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
    )
    existing_tables = set(existing_tables_raw.splitlines()) if existing_tables_raw else set()

    for table in EXPECTED_TABLES:
        if table not in existing_tables:
            errors.append(f"MISSING TABLE: {table}")

    # 2. Check expected columns
    for table, column, dtype_fragment in EXPECTED_COLUMNS:
        if table not in existing_tables:
            continue  # already reported as missing table
        result = psql(
            f"SELECT data_type FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}' AND column_name='{column}';"
        )
        if not result:
            errors.append(f"MISSING COLUMN: {table}.{column}")
        elif dtype_fragment not in result:
            errors.append(f"WRONG TYPE: {table}.{column} expected '{dtype_fragment}' got '{result}'")

    # 3. Check forbidden columns are absent
    for table, column in FORBIDDEN_COLUMNS:
        if table not in existing_tables:
            continue
        result = psql(
            f"SELECT 1 FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}' AND column_name='{column}';"
        )
        if result:
            errors.append(f"FORBIDDEN COLUMN still present: {table}.{column}")

    # 4. Check unique constraint on user_info.user_name
    result = psql(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "WHERE tc.table_name='user_info' AND ccu.column_name='user_name' "
        "  AND tc.constraint_type='UNIQUE';"
    )
    if not result:
        errors.append("MISSING CONSTRAINT: user_info.user_name UNIQUE")

    # 5. Check trigger on rows table
    result = psql(
        "SELECT 1 FROM information_schema.triggers "
        "WHERE event_object_table='rows' AND trigger_name='trg_rows_row_number';"
    )
    if not result:
        errors.append("MISSING TRIGGER: rows.trg_rows_row_number")

    if errors:
        print("\n[verify] SCHEMA VERIFICATION FAILED:")
        for err in errors:
            print(f"  ✗ {err}")
        raise AssertionError(f"{len(errors)} schema error(s) found")

    print(f"[verify] Schema OK — {len(EXPECTED_COLUMNS)} columns verified across {len(EXPECTED_TABLES)} tables.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  LatticeCast — Migration Test")
    print("=" * 60)

    # Cleanup any leftover container from a previous failed run
    run(["docker", "stop", CONTAINER_NAME], check=False, capture=True)

    try:
        start_container()
        wait_for_pg()
        run_migrations()
        verify_schema()
        print("\n" + "=" * 60)
        print("  ALL MIGRATION TESTS PASSED")
        print("=" * 60 + "\n")
    except Exception as exc:
        print(f"\n✗ MIGRATION TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        stop_container()


if __name__ == "__main__":
    main()
