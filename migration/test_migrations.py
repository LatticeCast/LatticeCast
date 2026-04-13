#!/usr/bin/env python3
"""
Migration test orchestrator — spins up a temporary PostgreSQL container,
runs all migration/*.sql files, then triggers each sub-test module.

Sub-tests:
  test_migration_schema.py  — table/column structure
  test_migration_rls.py     — RLS policies

Usage:
    python migration/test_migrations.py
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
PG_PORT = 15433

MIGRATION_DIR = Path(__file__).parent

MIGRATION_SORT_OVERRIDES: dict[str, str] = {
    "0022_workspace_merge_name.sql": "0017a_workspace_merge_name.sql",
    "0021_tables_reorder.sql": "0018a_tables_reorder.sql",
    "0023_user_info_rename_display_id.sql": "0019a_user_info_rename_display_id.sql",
}


def _migration_sort_key(path: Path) -> str:
    return MIGRATION_SORT_OVERRIDES.get(path.name, path.name)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def psql(sql: str) -> str:
    result = run(
        ["docker", "exec", CONTAINER_NAME,
         "psql", f"--username={PG_USER}", f"--dbname={PG_DB}",
         "--no-password", "--tuples-only", "--no-align",
         "--command", sql],
        capture=True,
    )
    return result.stdout.strip()


def psql_file(path: Path) -> None:
    run(
        ["docker", "exec", "--interactive", CONTAINER_NAME,
         "psql", f"--username={PG_USER}", f"--dbname={PG_DB}",
         "--no-password", "--set", "ON_ERROR_STOP=1",
         "--file", f"/migration/{path.name}"]
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


# ── Sub-test runner ───────────────────────────────────────────────────────────

def run_subtests() -> None:
    """Import and run each test_migration_*.py module."""
    import test_migration_schema
    import test_migration_rls

    subtests = [
        ("schema", test_migration_schema),
        ("rls", test_migration_rls),
    ]

    total_checks = 0
    all_errors: list[str] = []

    for name, module in subtests:
        print(f"\n[test:{name}] Running…")
        errors = module.verify(psql)
        if errors:
            for err in errors:
                print(f"  ✗ {err}")
            all_errors.extend(errors)
        else:
            print(f"  ✓ {name} passed")
        total_checks += 1

    if all_errors:
        print(f"\n[verify] FAILED: {len(all_errors)} error(s) across {total_checks} test(s)")
        raise AssertionError(f"{len(all_errors)} error(s)")
    else:
        print(f"\n[verify] All {total_checks} sub-test(s) passed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  LatticeCast — Migration Test")
    print("=" * 60)

    run(["docker", "stop", CONTAINER_NAME], check=False, capture=True)

    try:
        start_container()
        wait_for_pg()
        run_migrations()
        run_subtests()
        print("\n" + "=" * 60)
        print("  ALL MIGRATION TESTS PASSED")
        print("=" * 60 + "\n")
    except Exception as exc:
        print(f"\n✗ MIGRATION TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        stop_container()


if __name__ == "__main__":
    # Add migration dir to path so sub-tests can be imported
    sys.path.insert(0, str(MIGRATION_DIR))
    main()
