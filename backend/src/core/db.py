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


# --------------------------------------------------
# RUN MIGRATIONS
# --------------------------------------------------


async def _run_migrations(engine: AsyncEngine):
    """
    Run SQL migration files from migration/ directory.
    Files are executed in alphabetical order (e.g., 001_*, 002_*).
    Each statement is executed separately (asyncpg requirement).
    """
    if not MIGRATION_DIR.exists():
        print(f"⚠️ Migration directory not found: {MIGRATION_DIR}")
        return

    sql_files = sorted(MIGRATION_DIR.glob("*.sql"))
    if not sql_files:
        print("⚠️ No migration files found")
        return

    async with engine.begin() as conn:
        for sql_file in sql_files:
            print(f"📄 Running migration: {sql_file.name}")
            sql_content = sql_file.read_text()
            # Split by semicolon and execute each statement separately
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]
            for stmt in statements:
                # Skip comments-only statements
                if stmt.startswith("--") and "\n" not in stmt:
                    continue
                await conn.execute(text(stmt))

    print(f"✅ Executed {len(sql_files)} migration(s)")


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
