# src/core/db.py

import asyncio

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings

# app_engine: general API — CRUD on public, SELECT on auth
app_engine: AsyncEngine | None = None
app_session_factory: sessionmaker | None = None

# login_engine: auth endpoints — CRUD on auth schema only
login_engine: AsyncEngine | None = None
login_session_factory: sessionmaker | None = None


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


# --------------------------------------------------
# RLS IDENTITY HYGIENE
# --------------------------------------------------
#
# `app.current_user_id` is a session-level GUC, and SQLAlchemy's pool returns a
# connection to the pool with only a ROLLBACK -- the asyncpg dialect never
# issues DISCARD ALL / RESET ALL, so the value survives checkin. A request that
# never sets an identity (the pre-token lookups, or any future route that
# forgets get_rls_session) would then be authorised as whoever used that
# connection last, which is a cross-user read rather than a denial.
#
# Clearing the setting on every checkout makes the failure mode "no identity"
# instead: current_user_workspaces() maps '' to NULL, its set is empty, and
# every policy denies -- the deny-by-default the V52 policies were written for.

RLS_IDENTITY_SETTING = "app.current_user_id"


def clear_rls_identity(dbapi_connection, _record=None, _proxy=None) -> None:
    """Strip an inherited RLS identity from a connection leaving the pool.

    set_config rather than RESET: a custom GUC has no registered default, and
    '' is exactly what current_user_workspaces() turns into NULL.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SELECT set_config('{RLS_IDENTITY_SETTING}', '', false)")
    finally:
        cursor.close()


def install_rls_reset_hook(engine: AsyncEngine) -> None:
    """Run `clear_rls_identity` on every checkout of `engine`. Idempotent."""
    sync_engine = engine.sync_engine
    if not event.contains(sync_engine, "checkout", clear_rls_identity):
        event.listen(sync_engine, "checkout", clear_rls_identity)


# Clearing on checkout stops an identity leaking into the next request, but a
# commit ends the transaction and returns the connection, so the *next*
# statement of the same request can land on a different, identity-free
# connection -- and a policy then denies a row the caller just wrote (the
# workspace-rename refresh is the classic case). Re-apply the request's
# identity whenever a transaction begins, which is where a swapped connection
# first becomes visible.


def apply_rls_identity(session, _transaction, connection) -> None:
    """Set the session's RLS identity on the connection a transaction opened."""
    user_id = session.info.get("rls_user_id")
    if not user_id:
        return
    connection.execute(
        text("SELECT set_config(:setting, :uid, false)"),
        {"setting": RLS_IDENTITY_SETTING, "uid": str(user_id)},
    )


def install_rls_identity_hook() -> None:
    """Apply `apply_rls_identity` at the start of every ORM transaction. Idempotent."""
    if not event.contains(Session, "after_begin", apply_rls_identity):
        event.listen(Session, "after_begin", apply_rls_identity)


async def init_db():
    """
    Initialize async engines & session factories:
      - app_engine:   general API     (search_path=public,auth,gdpr)
      - login_engine: auth endpoints  (search_path=auth,gdpr)
    Migrations are handled by the migrate container, not the backend.

    v40: gdpr schema holds user_info (PII + handle + config). Both
    engines need it on search_path so unqualified joins work.
    """
    global app_engine, app_session_factory
    global login_engine, login_session_factory

    if app_engine:
        return app_engine

    db = settings.database
    app_url = db.app_async_url
    login_url = db.login_async_url

    for attempt in range(5):
        try:
            app_engine = _make_engine(app_url, "public,auth,gdpr")
            login_engine = _make_engine(login_url, "public,auth,gdpr")

            # The app engine carries per-request RLS identities; the login
            # engine runs as mgr_user (BYPASSRLS) and never reads the setting.
            install_rls_reset_hook(app_engine)
            install_rls_identity_hook()

            app_session_factory = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
            login_session_factory = sessionmaker(login_engine, class_=AsyncSession, expire_on_commit=False)

            # Test connection
            async with app_engine.begin() as conn:
                await conn.run_sync(lambda _: None)

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
    """FastAPI dependency — app_engine session (CRUD on public, SELECT on auth)."""
    global app_session_factory
    if not app_session_factory:
        await init_db()
    async with app_session_factory() as session:
        yield session


async def get_login_session() -> AsyncSession:
    """FastAPI dependency — login_engine session (CRUD on auth schema only)."""
    global login_session_factory
    if not login_session_factory:
        await init_db()
    async with login_session_factory() as session:
        yield session


async def set_rls_context(session: AsyncSession, user_id: str) -> None:
    """Store and apply the current request's PG RLS user context.

    Session-level on purpose: the pool wipes the setting on every checkout (see
    ``install_rls_reset_hook``), so it can never outlive the request that set it.
    """
    session.info["rls_user_id"] = str(user_id)
    await session.execute(text("SELECT set_config('app.current_user_id', :uid, false)").bindparams(uid=str(user_id)))


async def reapply_rls_context(session: AsyncSession) -> None:
    """Re-apply PG RLS user context after a commit may swap connections.

    The checkout hook guarantees a recycled connection carries no identity; it
    cannot restore *this* request's, so any statement issued after a commit has
    to re-establish it.
    """
    user_id = session.info.get("rls_user_id")
    if user_id:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)").bindparams(uid=str(user_id))
        )


# --------------------------------------------------
# SHUTDOWN
# --------------------------------------------------


async def close_db():
    """Dispose all SQLAlchemy engines."""
    global app_engine, login_engine

    for eng in [app_engine, login_engine]:
        if eng:
            await eng.dispose()
    app_engine = login_engine = None
    print("✅ Database engines closed")
