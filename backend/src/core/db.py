# src/core/db.py

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from config.settings import settings

engine: AsyncEngine | None = None
async_session_factory: sessionmaker | None = None

MIGRATION_DIR = Path("/migration")


def _split_sql(sql: str) -> list[str]:
    """
    Split SQL into individual statements on semicolons, skipping semicolons
    inside dollar-quoted blocks ($$...$$) and single-line comments.
    Dollar-quote tags must be $$ or $word$ (letters/digits/underscore only).
    Returns only non-empty, non-comment-only statements.
    """
    import re
    dollar_tag_re = re.compile(r'\$([A-Za-z0-9_]*)\$')

    statements: list[str] = []
    current: list[str] = []
    in_dollar_quote = False
    dollar_tag = ""
    i = 0

    while i < len(sql):
        # Detect start of dollar-quoted block ($$...$$  or $tag$...$tag$)
        if not in_dollar_quote:
            m = dollar_tag_re.match(sql, i)
            if m:
                tag = m.group(0)
                in_dollar_quote = True
                dollar_tag = tag
                current.append(tag)
                i = m.end()
                continue
        elif sql[i : i + len(dollar_tag)] == dollar_tag:
            current.append(dollar_tag)
            i += len(dollar_tag)
            in_dollar_quote = False
            dollar_tag = ""
            continue

        if not in_dollar_quote and sql[i] == ";":
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

    # Flush remaining
    stmt = "".join(current).strip()
    lines = [ln.strip() for ln in stmt.splitlines()
             if ln.strip() and not ln.strip().startswith("--")]
    if lines:
        statements.append(stmt)

    return statements


# --------------------------------------------------
# RUN MIGRATIONS
# --------------------------------------------------


async def _run_migrations(engine: AsyncEngine):
    """
    Run SQL migration files from migration/ directory.
    Files are executed in alphabetical order (e.g., 001_*, 002_*).
    Each migration file is tracked in schema_migrations to prevent re-running.
    """
    if not MIGRATION_DIR.exists():
        print(f"⚠️ Migration directory not found: {MIGRATION_DIR}")
        return

    sql_files = sorted(MIGRATION_DIR.glob("*.sql"))
    if not sql_files:
        print("⚠️ No migration files found")
        return

    # Validate: migration numbers must be unique (extract number from <number>_<name>.sql)
    seen_numbers: dict[int, str] = {}
    for f in sql_files:
        parts = f.stem.split("_", 1)
        try:
            num = int(parts[0])
            if num in seen_numbers:
                raise RuntimeError(
                    f"❌ Duplicate migration number {num}: {seen_numbers[num]} and {f.name}"
                )
            seen_numbers[num] = f.name
        except ValueError:
            raise RuntimeError(f"❌ Invalid migration filename: {f.name} — must start with <number>_")

    async with engine.begin() as conn:
        # Create migration tracking table if it doesn't exist
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  filename VARCHAR PRIMARY KEY,"
            "  applied_at TIMESTAMP NOT NULL DEFAULT NOW()"
            ")"
        ))

        for sql_file in sql_files:
            # Check if already applied
            result = await conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE filename = :fn"),
                {"fn": sql_file.name},
            )
            if result.scalar_one_or_none() is not None:
                print(f"⏭️  Skipping already-applied migration: {sql_file.name}")
                continue

            print(f"📄 Running migration: {sql_file.name}")
            sql_content = sql_file.read_text()
            # Split by semicolon, respecting dollar-quoted blocks ($$...$$)
            statements = _split_sql(sql_content)
            for stmt in statements:
                await conn.execute(text(stmt))

            # Record as applied
            await conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:fn)"),
                {"fn": sql_file.name},
            )
            print(f"✅ Applied migration: {sql_file.name}")

    print(f"✅ Migration check complete ({len(sql_files)} file(s) checked)")


# --------------------------------------------------
# INIT DB
# --------------------------------------------------


async def init_db(run_migrations: bool = False):
    """
    Initialize async engine & session factory.
    Optionally run SQL migrations from migration/*.sql files.
    """
    global engine, async_session_factory

    if engine:
        return engine

    database_url = settings.database.async_url

    for attempt in range(5):
        try:
            engine = create_async_engine(
                database_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
            )

            async_session_factory = sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Test connection
            async with engine.begin() as conn:
                await conn.run_sync(lambda _: None)

            print("✅ Connected to PostgreSQL")

            if run_migrations:
                await _run_migrations(engine)

            return engine

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1}/5 DB init failed: {e}")
            await asyncio.sleep(3)

    raise RuntimeError("❌ Could not connect to PostgreSQL after multiple attempts")


# --------------------------------------------------
# SESSION DEPENDENCY
# --------------------------------------------------


async def get_session() -> AsyncSession:
    """
    FastAPI dependency for DB session
    """
    global async_session_factory

    if not async_session_factory:
        await init_db(run_migrations=False)

    async with async_session_factory() as session:
        yield session


# --------------------------------------------------
# SHUTDOWN
# --------------------------------------------------


async def close_db():
    """Dispose SQLAlchemy engine."""
    global engine

    if engine:
        await engine.dispose()
        engine = None
        print("✅ Database engine closed")
