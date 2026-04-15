# src/core/db.py

import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from config.settings import settings

# app_engine: general API — CRUD on public, SELECT on auth
app_engine: AsyncEngine | None = None
app_session_factory: sessionmaker | None = None

# login_engine: auth endpoints — CRUD on auth schema only
login_engine: AsyncEngine | None = None
login_session_factory: sessionmaker | None = None

# Backward-compat alias — callers importing `engine` still work
engine: AsyncEngine | None = None
async_session_factory: sessionmaker | None = None


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


async def init_db():
    """
    Initialize async engines & session factories:
      - app_engine:   general API     (search_path=public,auth)
      - login_engine: auth endpoints  (search_path=auth)
    Migrations are handled by the migrate container, not the backend.
    """
    global engine, async_session_factory
    global app_engine, app_session_factory
    global login_engine, login_session_factory

    if app_engine:
        return app_engine

    db = settings.database
    app_url = db.app_async_url
    login_url = db.login_async_url

    for attempt in range(5):
        try:
            app_engine = _make_engine(app_url, "public,auth")
            login_engine = _make_engine(login_url, "auth")

            app_session_factory = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
            login_session_factory = sessionmaker(login_engine, class_=AsyncSession, expire_on_commit=False)

            # Test connection
            async with app_engine.begin() as conn:
                await conn.run_sync(lambda _: None)

            # Backward-compat aliases
            engine = app_engine
            async_session_factory = app_session_factory

            print("✅ Connected to PostgreSQL")
            return app_engine

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1}/5 DB init failed: {e}")
            await asyncio.sleep(3)

    raise RuntimeError("❌ Could not connect to PostgreSQL after multiple attempts")


# --------------------------------------------------
# SESSION DEPENDENCY
# --------------------------------------------------


async def get_session() -> AsyncSession:
    """FastAPI dependency — app_engine session. Force rollback to prevent idle-in-tx leaks."""
    global app_session_factory

    if not app_session_factory:
        await init_db()

    async with app_session_factory() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


async def get_login_session() -> AsyncSession:
    """FastAPI dependency — login_engine session. Force rollback to prevent idle-in-tx leaks."""
    global login_session_factory

    if not login_session_factory:
        await init_db()

    async with login_session_factory() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


# --------------------------------------------------
# SHUTDOWN
# --------------------------------------------------


async def close_db():
    """Dispose all SQLAlchemy engines."""
    global engine, app_engine, login_engine

    for eng in [app_engine, login_engine]:
        if eng:
            await eng.dispose()
    app_engine = login_engine = engine = None
    print("✅ Database engines closed")
