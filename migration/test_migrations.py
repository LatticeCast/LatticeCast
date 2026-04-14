#!/usr/bin/env python3
"""
Migration test runner — applies migrations via Atlas, then runs sub-test modules
against the resulting schema.

Sub-tests:
  test_migration_schema.py  — table/column structure
  test_migration_rls.py     — RLS policies

Usage:
    python migration/test_migrations.py
"""

import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CONTAINER_NAME = "latticecast-migration-test"
PG_IMAGE = "postgres:18"
PG_USER = "dba_user"
PG_PASSWORD = "dba_pws"
PG_DB = "testdb"

MIGRATION_DIR = Path(__file__).parent


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


# ── Sub-test runner ───────────────────────────────────────────────────────────

def run_subtests() -> None:
    """Import and run each test_migration_*.py module."""
    import test_migration_schema
    import test_migration_rls

    subtests = [
        ("schema", test_migration_schema),
        ("rls", test_migration_rls),
    ]

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

    if all_errors:
        print(f"\n[verify] FAILED: {len(all_errors)} error(s)")
        raise AssertionError(f"{len(all_errors)} error(s)")
    else:
        print(f"\n[verify] All {len(subtests)} sub-test(s) passed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  LatticeCast — Migration Test (Atlas + verify)")
    print("=" * 60)

    # Clean up any leftover container
    run(["docker", "stop", CONTAINER_NAME], check=False, capture=True)

    try:
        # Start temporary PG container
        print(f"[start] Starting temporary PostgreSQL container ({PG_IMAGE})…")
        run([
            "docker", "run", "--rm", "--detach",
            "--name", CONTAINER_NAME,
            "--env", f"POSTGRES_USER={PG_USER}",
            "--env", f"POSTGRES_PASSWORD={PG_PASSWORD}",
            "--env", f"POSTGRES_DB={PG_DB}",
            "--volume", f"{MIGRATION_DIR.resolve()}:/migrations:ro",
            PG_IMAGE,
        ])

        # Wait for PG
        import time
        print("[wait]  Waiting for PostgreSQL…")
        for _ in range(30):
            r = run(["docker", "exec", CONTAINER_NAME, "pg_isready", "-U", PG_USER, "-d", PG_DB],
                    check=False, capture=True)
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL did not become ready")

        db_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@localhost:5432/{PG_DB}?sslmode=disable"
        atlas_base = [
            "docker", "run", "--rm",
            "--network", f"container:{CONTAINER_NAME}",
            "--volume", f"{MIGRATION_DIR.resolve()}:/migrations:ro",
            "arigaio/atlas:latest",
        ]

        # Apply migrations
        print("[migrate] Applying migrations via Atlas…")
        run(atlas_base + [
            "migrate", "apply",
            "--dir", "file:///migrations",
            "--url", db_url,
        ])
        print("[migrate] All migrations applied.")

        # Run verification tests
        run_subtests()

        print("\n" + "=" * 60)
        print("  ALL MIGRATION TESTS PASSED")
        print("=" * 60 + "\n")
    except Exception as exc:
        print(f"\n✗ MIGRATION TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        print("[stop]  Stopping container…")
        run(["docker", "stop", CONTAINER_NAME], check=False, capture=True)


if __name__ == "__main__":
    sys.path.insert(0, str(MIGRATION_DIR))
    main()
