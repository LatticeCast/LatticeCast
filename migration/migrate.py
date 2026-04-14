#!/usr/bin/env python3
"""
Migration runner — lint, test on temp DB, then apply to real DB.

Flow:
  1. SQLFluff lint (static analysis)
  2. Apply to temp DB → run schema/RLS verification
  3. Apply to real DB

Usage:
  python migrate.py                  # full flow: lint → test → apply
  python migrate.py --apply-only     # skip lint/test, apply directly
  python migrate.py --test-only      # lint + test only, no apply
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

MIGRATION_DIR = Path(__file__).parent
PG_IMAGE = "postgres:18"
TEST_CONTAINER = "latticecast-migration-test"
TEST_USER = "dba_user"
TEST_PASSWORD = "dba_pws"
TEST_DB = "testdb"


# ── SQL splitter (handles $$ dollar-quoting) ─────────────────────────────────

def split_sql(sql: str) -> list[str]:
    """Split SQL on semicolons, respecting $$...$$ blocks."""
    dollar_tag_re = re.compile(r'\$([A-Za-z0-9_]*)\$')
    statements, current = [], []
    in_dollar, dollar_tag, i = False, "", 0

    while i < len(sql):
        if not in_dollar:
            m = dollar_tag_re.match(sql, i)
            if m:
                in_dollar, dollar_tag = True, m.group(0)
                current.append(dollar_tag)
                i = m.end()
                continue
        elif sql[i:i + len(dollar_tag)] == dollar_tag:
            current.append(dollar_tag)
            i += len(dollar_tag)
            in_dollar, dollar_tag = False, ""
            continue

        if not in_dollar and sql[i] == ";":
            stmt = "".join(current).strip()
            lines = [ln.strip() for ln in stmt.splitlines()
                     if ln.strip() and not ln.strip().startswith("--")]
            if lines:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(sql[i])
        i += 1

    stmt = "".join(current).strip()
    lines = [ln.strip() for ln in stmt.splitlines()
             if ln.strip() and not ln.strip().startswith("--")]
    if lines:
        statements.append(stmt)
    return statements


# ── Apply migrations via psycopg2 ────────────────────────────────────────────

def apply_migrations(dsn: str) -> None:
    """Apply all pending V*.sql migrations to the given database."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  filename VARCHAR PRIMARY KEY,"
        "  applied_at TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    )

    sql_files = sorted(MIGRATION_DIR.glob("V*.sql"),
                       key=lambda f: int(re.match(r'V(\d+)__', f.name).group(1)))
    for sql_file in sql_files:
        cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (sql_file.name,))
        if cur.fetchone():
            print(f"  ⏭️  {sql_file.name}")
            continue

        print(f"  📄 {sql_file.name}")
        content = sql_file.read_text()
        # Strip jetbase headers
        content = re.sub(r'^-- upgrade\s*\n', '', content)
        content = re.sub(r'\n-- rollback[\s\S]*$', '', content)

        for stmt in split_sql(content):
            cur.execute(stmt)

        cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (sql_file.name,))

    cur.close()
    conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def psql_query(sql: str) -> str:
    """Run SQL against the test container."""
    result = run(
        ["docker", "exec", TEST_CONTAINER,
         "psql", f"--username={TEST_USER}", f"--dbname={TEST_DB}",
         "--no-password", "--tuples-only", "--no-align",
         "--command", sql],
        capture=True,
    )
    return result.stdout.strip()


# ── Steps ────────────────────────────────────────────────────────────────────

def step_lint() -> bool:
    """Run SQLFluff lint on migration files."""
    print("\n[1/3] SQLFluff lint")
    sql_files = sorted(MIGRATION_DIR.glob("V*.sql"),
                       key=lambda f: int(re.match(r'V(\d+)__', f.name).group(1)))
    if not sql_files:
        print("  ⚠️  No SQL files found")
        return False

    result = run(
        ["sqlfluff", "lint", "--dialect", "postgres"] + [str(f) for f in sql_files],
        check=False, capture=True,
    )
    if result.returncode == 0:
        print("  ✓ lint passed")
        return True
    else:
        # SQLFluff returns 1 for violations — print but don't block for now
        print(f"  ⚠️  lint warnings:\n{result.stdout[:500]}")
        return True  # treat as warning, not failure


def step_test() -> bool:
    """Apply to temp DB, verify schema + RLS."""
    print("\n[2/3] Test migrations on temp DB")

    # Clean up leftover
    run(["docker", "stop", TEST_CONTAINER], check=False, capture=True)

    try:
        print("  Starting temp PostgreSQL…")
        run([
            "docker", "run", "--rm", "--detach",
            "--name", TEST_CONTAINER,
            "--network", os.environ.get("TEST_NETWORK", "bridge"),
            "--env", f"POSTGRES_USER={TEST_USER}",
            "--env", f"POSTGRES_PASSWORD={TEST_PASSWORD}",
            "--env", f"POSTGRES_DB={TEST_DB}",
            PG_IMAGE,
        ])

        # Wait for ready
        for _ in range(30):
            r = run(["docker", "exec", TEST_CONTAINER, "pg_isready", "-U", TEST_USER, "-d", TEST_DB],
                    check=False, capture=True)
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            print("  ✗ PostgreSQL did not start")
            return False

        # Apply to temp DB
        print("  Applying migrations…")
        test_dsn = f"postgresql://{TEST_USER}:{TEST_PASSWORD}@{TEST_CONTAINER}:5432/{TEST_DB}"
        apply_migrations(test_dsn)
        print("  ✓ Migrations applied")

        # Verify
        sys.path.insert(0, str(Path(__file__).parent))
        import test_migration_schema
        import test_migration_rls

        all_errors = []
        for name, module in [("schema", test_migration_schema), ("rls", test_migration_rls)]:
            errors = module.verify(psql_query)
            if errors:
                for err in errors:
                    print(f"  ✗ {name}: {err}")
                all_errors.extend(errors)
            else:
                print(f"  ✓ {name} passed")

        if all_errors:
            print(f"  ✗ {len(all_errors)} error(s)")
            return False

        return True
    finally:
        run(["docker", "stop", TEST_CONTAINER], check=False, capture=True)


def step_apply() -> bool:
    """Apply migrations to real DB."""
    print("\n[3/3] Apply to real DB")
    dsn = os.environ.get("DATABASE_URL", "postgresql://dba_user:dba_pws@db:5432/db")
    apply_migrations(dsn)
    print("  ✓ Real DB migrated")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 50)
    print("  LatticeCast — Migration")
    print("=" * 50)

    test_only = "--test-only" in sys.argv
    apply_only = "--apply-only" in sys.argv

    if apply_only:
        if not step_apply():
            sys.exit(1)
    else:
        if not step_lint():
            sys.exit(1)
        if not step_test():
            sys.exit(1)
        if not test_only:
            if not step_apply():
                sys.exit(1)

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
