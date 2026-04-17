#!/usr/bin/env python3
"""
Migration runner — lint, test on temp DB, then apply to real DB.

Flow:
  1. SQLFluff lint (static analysis)
  2. Apply to temp DB → run schema/RLS verification
  3. Apply to real DB

Usage:
  python migrate.py                  # full flow: lint → verify checksums → test → apply
  python migrate.py --apply-only     # skip lint/test, apply directly
  python migrate.py --test-only      # lint + test only, no apply
  python migrate.py --hash           # (re)generate checksums.txt from current V*.sql
"""

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

MIGRATION_DIR = Path(__file__).parent
CHECKSUMS_FILE = MIGRATION_DIR / "checksums.txt"
PG_IMAGE = "postgres:18"
TEST_CONTAINER = "latticecast-migration-test"
TEST_USER = "dba_user"
TEST_PASSWORD = "dba_pws"
TEST_DB = "testdb"


# ── SQL splitter (handles $$ dollar-quoting) ─────────────────────────────────

def split_sql(sql: str) -> list[str]:
    """Split SQL on `;` at top level.

    Tracks four contexts where `;` is not a statement terminator:
      - `$$...$$` / `$tag$...$tag$` dollar-quoted blocks
      - `'...'` single-quoted string literals (with `''` escape)
      - `"..."` double-quoted identifiers (with `""` escape)
      - `-- ... \n` single-line comments
      - `/* ... */` C-style block comments
    """
    dollar_tag_re = re.compile(r'\$([A-Za-z0-9_]*)\$')
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    dollar_tag = ""
    in_sq = False        # single-quoted string
    in_dq = False        # double-quoted identifier
    in_line_comment = False
    in_block_comment = False
    n = len(sql)
    i = 0

    def _emit():
        stmt = "".join(current).strip()
        lines = [
            ln.strip() for ln in stmt.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        if lines:
            statements.append(stmt)

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_sq:
            current.append(ch)
            if ch == "'" and nxt == "'":
                current.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_sq = False
            i += 1
            continue
        if in_dq:
            current.append(ch)
            if ch == '"' and nxt == '"':
                current.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_dq = False
            i += 1
            continue
        if in_dollar:
            if sql[i:i + len(dollar_tag)] == dollar_tag:
                current.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar = False
                dollar_tag = ""
                continue
            current.append(ch)
            i += 1
            continue

        # Top level — detect context openers
        if ch == "-" and nxt == "-":
            current.append(ch)
            current.append(nxt)
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            current.append(ch)
            current.append(nxt)
            in_block_comment = True
            i += 2
            continue
        if ch == "'":
            current.append(ch)
            in_sq = True
            i += 1
            continue
        if ch == '"':
            current.append(ch)
            in_dq = True
            i += 1
            continue
        m = dollar_tag_re.match(sql, i)
        if m:
            dollar_tag = m.group(0)
            in_dollar = True
            current.append(dollar_tag)
            i = m.end()
            continue

        if ch == ";":
            _emit()
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    _emit()
    return statements


# ── Apply migrations via psycopg2 ────────────────────────────────────────────

def _checksum(content: str) -> str:
    """SHA-256 of migration file content (hex)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_sql_files() -> list[Path]:
    return sorted(
        MIGRATION_DIR.glob("V*.sql"),
        key=lambda f: int(re.match(r'V(\d+)__', f.name).group(1)),
    )


def _current_checksums() -> dict[str, str]:
    return {f.name: _checksum(f.read_text()) for f in _sorted_sql_files()}


def _read_checksums_file() -> dict[str, str]:
    if not CHECKSUMS_FILE.exists():
        return {}
    result = {}
    for line in CHECKSUMS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        result[parts[0]] = parts[1]
    return result


def _write_checksums_file(checksums: dict[str, str]) -> None:
    lines = ["# Generated by migrate.py --hash. Commit this file.",
             "# filename  sha256"]
    for name in sorted(checksums, key=lambda n: int(re.match(r'V(\d+)__', n).group(1))):
        lines.append(f"{name}  {checksums[name]}")
    CHECKSUMS_FILE.write_text("\n".join(lines) + "\n")


def apply_migrations(dsn: str) -> None:
    """Apply all pending V*.sql migrations. Verify checksum on already-applied files.

    Tracking table lives in the `private` schema — DBA-only. Regular app/login
    roles cannot see or modify migration state.
    """
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    # Bootstrap: V1 creates private.schema_migrations, but on a truly fresh DB
    # we need the table to exist before V1 can be recorded. So we create it
    # idempotently here — V1 is also idempotent and will be a no-op.
    cur.execute("CREATE SCHEMA IF NOT EXISTS private")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS private.schema_migrations ("
        "  filename VARCHAR PRIMARY KEY,"
        "  checksum VARCHAR NOT NULL DEFAULT '',"
        "  applied_at TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    )

    sql_files = sorted(MIGRATION_DIR.glob("V*.sql"),
                       key=lambda f: int(re.match(r'V(\d+)__', f.name).group(1)))

    # Report current DB state
    cur.execute("SELECT filename FROM private.schema_migrations ORDER BY filename")
    applied = {r[0] for r in cur.fetchall()}
    current_ver = max(
        (int(re.match(r'V(\d+)__', n).group(1)) for n in applied),
        default=0,
    )
    pending = [f for f in sql_files if f.name not in applied]
    print(f"  DB at V{current_ver} ({len(applied)} applied), "
          f"{len(pending)} pending")

    for sql_file in sql_files:
        content = sql_file.read_text()
        csum = _checksum(content)

        cur.execute(
            "SELECT checksum FROM private.schema_migrations WHERE filename = %s",
            (sql_file.name,),
        )
        row = cur.fetchone()
        if row is not None:
            stored = row[0]
            if stored and stored != csum:
                raise RuntimeError(
                    f"❌ Checksum mismatch: {sql_file.name}\n"
                    f"   stored:  {stored}\n"
                    f"   current: {csum}\n"
                    f"   Migration file was modified after being applied."
                )
            if not stored:
                cur.execute(
                    "UPDATE private.schema_migrations SET checksum = %s "
                    "WHERE filename = %s",
                    (csum, sql_file.name),
                )
            print(f"  ⏭️  {sql_file.name}")
            continue

        print(f"  📄 {sql_file.name}")
        body = re.sub(r'^-- upgrade\s*\n', '', content)
        body = re.sub(r'\n-- rollback[\s\S]*$', '', body)

        for stmt in split_sql(body):
            try:
                cur.execute(stmt)
            except Exception:
                print(f"  FAILED on stmt: {stmt[:300]}")
                raise

        cur.execute(
            "INSERT INTO private.schema_migrations (filename, checksum) "
            "VALUES (%s, %s)",
            (sql_file.name, csum),
        )

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

def step_checksum_verify() -> bool:
    """Verify checksums.txt matches current V*.sql file contents."""
    print("\n[checksum] Verify checksums.txt")
    stored = _read_checksums_file()
    current = _current_checksums()

    if not stored:
        print("  ✗ checksums.txt missing. Run: python migrate.py --hash")
        return False

    missing = set(current) - set(stored)
    extra = set(stored) - set(current)
    mismatch = [n for n in current if n in stored and current[n] != stored[n]]

    if missing or extra or mismatch:
        for n in missing:
            print(f"  ✗ not in checksums.txt: {n}")
        for n in extra:
            print(f"  ✗ in checksums.txt but file missing: {n}")
        for n in mismatch:
            print(f"  ✗ checksum mismatch: {n}")
        print("  Run: python migrate.py --hash  (and commit the result)")
        return False

    print(f"  ✓ {len(current)} file(s) match checksums.txt")
    return True


def step_lint() -> bool:
    """Run SQLFluff lint on migration files."""
    print("\n[1/3] SQLFluff lint")
    sql_files = _sorted_sql_files()
    if not sql_files:
        print("  ⚠️  No SQL files found")
        return False

    result = run(
        ["sqlfluff", "lint"] + [str(f) for f in sql_files],
        check=False, capture=True,
    )
    if result.returncode == 0:
        print("  ✓ lint passed")
        return True
    print(f"  ✗ lint failed:\n{result.stdout}")
    return False


def step_test() -> bool:
    """Apply to temp DB, verify schema + RLS."""
    print("\n[2/3] Test migrations on temp DB")

    # Clean up leftover
    run(["docker", "stop", TEST_CONTAINER], check=False, capture=True)

    try:
        print("  Starting temp PostgreSQL…")
        pg_host = os.environ.get("TEST_PG_HOST", TEST_CONTAINER)
        pg_port = os.environ.get("TEST_PG_PORT", "5432")
        run_args = [
            "docker", "run", "--rm", "--detach",
            "--name", TEST_CONTAINER,
            "--env", f"POSTGRES_USER={TEST_USER}",
            "--env", f"POSTGRES_PASSWORD={TEST_PASSWORD}",
            "--env", f"POSTGRES_DB={TEST_DB}",
        ]
        if pg_host == "localhost":
            run_args += ["--publish", f"{pg_port}:5432"]
        else:
            run_args += ["--network", os.environ.get("TEST_NETWORK", "bridge")]
        run_args.append(PG_IMAGE)
        run(run_args)

        # Wait for ready — retry actual connection, not just pg_isready
        test_dsn = f"postgresql://{TEST_USER}:{TEST_PASSWORD}@{pg_host}:{pg_port}/{TEST_DB}"
        for attempt in range(20):
            try:
                conn = psycopg2.connect(test_dsn)
                conn.close()
                break
            except psycopg2.OperationalError:
                time.sleep(1)
        else:
            print("  ✗ PostgreSQL did not start")
            return False

        # Apply to temp DB
        print("  Applying migrations…")
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

    if "--hash" in sys.argv:
        checksums = _current_checksums()
        _write_checksums_file(checksums)
        print(f"\n✅ Wrote {CHECKSUMS_FILE.name} ({len(checksums)} file(s)).")
        print("   Commit it alongside your SQL changes.")
        return

    test_only = "--test-only" in sys.argv
    apply_only = "--apply-only" in sys.argv

    if apply_only:
        if not step_checksum_verify():
            sys.exit(1)
        if not step_apply():
            sys.exit(1)
    else:
        if not step_lint():
            sys.exit(1)
        if not step_checksum_verify():
            sys.exit(1)
        if not step_test():
            sys.exit(1)
        if not test_only:
            if not step_apply():
                sys.exit(1)

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
