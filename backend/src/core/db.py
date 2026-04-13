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

# dba_engine: migrations only — full access (public, auth, private)
dba_engine: AsyncEngine | None = None
dba_session_factory: sessionmaker | None = None

# app_engine: general API — CRUD on public, SELECT on auth
app_engine: AsyncEngine | None = None
app_session_factory: sessionmaker | None = None

# login_engine: auth endpoints — CRUD on auth schema only
login_engine: AsyncEngine | None = None
login_session_factory: sessionmaker | None = None

# Backward-compat alias — callers importing `engine` still work
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


def _make_engine(url: str, search_path: str) -> AsyncEngine:
    return create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        connect_args={"server_settings": {"search_path": search_path}},
    )


async def init_db(run_migrations: bool = False):
    """
    Initialize async engines & session factories for all three DB roles:
      - dba_engine:   migrations only (search_path=public,auth,private)
      - app_engine:   general API     (search_path=public,auth)
      - login_engine: auth endpoints  (search_path=auth)
    Optionally run SQL migrations from migration/*.sql files via dba_engine.
    """
    global engine, async_session_factory
    global dba_engine, dba_session_factory
    global app_engine, app_session_factory
    global login_engine, login_session_factory

    if app_engine:
        return app_engine

    db = settings.database

    # Decide URLs: fall back to superuser if role passwords not configured
    dba_url = db.dba_async_url if db.dba_password else db.async_url
    app_url = db.app_async_url if db.app_password else db.async_url
    login_url = db.login_async_url if db.login_password else db.async_url

    for attempt in range(5):
        try:
            dba_engine = _make_engine(dba_url, "public,auth,private")
            app_engine = _make_engine(app_url, "public,auth")
            login_engine = _make_engine(login_url, "auth")

            dba_session_factory = sessionmaker(dba_engine, class_=AsyncSession, expire_on_commit=False)
            app_session_factory = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
            login_session_factory = sessionmaker(login_engine, class_=AsyncSession, expire_on_commit=False)

            # Test connection via app_engine
            async with app_engine.begin() as conn:
                await conn.run_sync(lambda _: None)

            # Backward-compat aliases
            engine = app_engine
            async_session_factory = app_session_factory

            print("✅ Connected to PostgreSQL")

            if run_migrations:
                await _run_migrations(dba_engine)

            return app_engine

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1}/5 DB init failed: {e}")
            await asyncio.sleep(3)

    raise RuntimeError("❌ Could not connect to PostgreSQL after multiple attempts")


# --------------------------------------------------
# SESSION DEPENDENCY
# --------------------------------------------------


async def get_session() -> AsyncSession:
    """
    FastAPI dependency — app_engine session (CRUD on public, SELECT on auth).
    Used by general API routes.
    """
    global app_session_factory

    if not app_session_factory:
        await init_db(run_migrations=False)

    async with app_session_factory() as session:
        yield session


async def get_login_session() -> AsyncSession:
    """
    FastAPI dependency — login_engine session (CRUD on auth schema only).
    Used by auth/login routes.
    """
    global login_session_factory

    if not login_session_factory:
        await init_db(run_migrations=False)

    async with login_session_factory() as session:
        yield session


# --------------------------------------------------
# SHUTDOWN
# --------------------------------------------------


async def close_db():
    """Dispose all SQLAlchemy engines."""
    global engine, dba_engine, app_engine, login_engine

    for eng, name in [
        (dba_engine, "dba"),
        (app_engine, "app"),
        (login_engine, "login"),
    ]:
        if eng:
            await eng.dispose()
    dba_engine = app_engine = login_engine = engine = None
    print("✅ Database engines closed")
