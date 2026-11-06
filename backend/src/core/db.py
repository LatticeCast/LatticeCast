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
# `app.current_user_id` is set with is_local=TRUE: a transaction-local GUC
# that PostgreSQL itself clears at COMMIT or ROLLBACK, on whichever physical
# connection the transaction happened to run on. That guarantee holds
# regardless of what sits between the app and PostgreSQL -- including an
# external transaction-mode pooler (e.g. PgBouncer), which hands each
# transaction of the same logical client session to a *different* backend
# connection. A session-level set (is_local=FALSE) would not survive that:
# the value lives on the backend connection, PgBouncer transaction mode does
# not guarantee a reset between transactions, and the next transaction --
# quite possibly a different tenant's request -- could inherit it. Scoping
# the GUC to the transaction removes that failure mode by construction rather
# than by a reset convention this app does not control.
#
# This app has no external pooler in front of it today (SQLAlchemy's own
# pool talks to PostgreSQL directly), so nothing observable changes yet --
# but it means a transaction-mode pooler can be introduced later purely as
# infrastructure, without re-deriving this identity story.
#
# Being transaction-local raises the bar on *when* the identity must be set:
# it has to be (re)applied inside every transaction before that transaction's
# first identity-dependent statement, with no exceptions -- a value from a
# prior transaction on the same session is gone by construction. The
# `after_begin` hook below (`apply_rls_identity`) is what makes that
# automatic: it fires at the start of every ORM transaction for the life of
# a session, re-reading the identity `set_rls_context` stashed in
# `session.info`, so one `set_rls_context` call per request is enough even
# across a mid-request commit.
#
# The checkout-time clear below (`clear_rls_identity`) predates this and is
# no longer load-bearing for cross-tenant isolation -- a transaction-local
# value cannot survive into a connection's next checkout in the first place.
# It stays as a second, independent layer: deny-by-default for any statement
# that somehow runs with no open transaction at all.
#
# NOT A TEMPLATE: this is the only place in the codebase that sets
# RLS_IDENTITY_SETTING with is_local=FALSE, and only ever to blank it. A real
# identity always goes through `set_rls_context`/`apply_rls_identity`
# (is_local=TRUE). Do not copy the is_local=FALSE shape below to set an
# actual user_id elsewhere -- that reintroduces the session-level leak this
# whole module exists to close.

RLS_IDENTITY_SETTING = "app.current_user_id"


def clear_rls_identity(dbapi_connection, _record=None, _proxy=None) -> None:
    """Strip an inherited RLS identity from a connection leaving the pool.

    set_config rather than RESET: a custom GUC has no registered default, and
    '' is exactly what current_user_workspaces() turns into NULL. Secondary
    defense only -- see the NOT A TEMPLATE note above this function: never
    pass a real user_id here with is_local=FALSE.
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


# A transaction-local GUC does not survive its own COMMIT, let alone a
# connection handoff -- so every transaction, not just the first, has to set
# it again before doing anything identity-dependent. Re-apply at
# `after_begin`, which is the one point guaranteed to run at the start of
# every ORM transaction for the life of a session.


def apply_rls_identity(session, _transaction, connection) -> None:
    """Set the RLS identity on the transaction a connection just opened.

    is_local=TRUE: scoped to this transaction only, cleared automatically by
    PostgreSQL at COMMIT/ROLLBACK regardless of which physical connection ran
    it -- see the RLS IDENTITY HYGIENE note above.
    """
    user_id = session.info.get("rls_user_id")
    if not user_id:
        return
    connection.execute(
        text("SELECT set_config(:setting, :uid, true)"),
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

    Two jobs, both needed: stash ``user_id`` on ``session.info`` so
    ``apply_rls_identity`` re-applies it on every later transaction this
    session opens (see the RLS IDENTITY HYGIENE note above); and set it on
    the transaction already open *right now* -- the caller
    (``get_rls_session``) typically runs after ``get_current_user`` already
    queried this same session, so a transaction is usually already in
    progress and ``after_begin`` will not fire again for it.
    """
    session.info["rls_user_id"] = str(user_id)
    await session.execute(
        text("SELECT set_config(:setting, :uid, true)"),
        {"setting": RLS_IDENTITY_SETTING, "uid": str(user_id)},
    )


async def reapply_rls_context(session: AsyncSession) -> None:
    """Explicitly (re-)apply this session's RLS identity before a read.

    Redundant with ``apply_rls_identity``'s ``after_begin`` hook in the
    common case (see the RLS IDENTITY HYGIENE note above). Kept as an
    explicit, auditable statement at call sites that read state a caller
    just wrote (e.g. after a commit), rather than relying solely on an event
    hook to have run correctly.
    """
    user_id = session.info.get("rls_user_id")
    if user_id:
        await session.execute(
            text("SELECT set_config(:setting, :uid, true)"),
            {"setting": RLS_IDENTITY_SETTING, "uid": str(user_id)},
        )


def get_fixed_identity_session(user_id: str):
    """Build a FastAPI dependency yielding an app session pinned to `user_id`.

    For intentionally public/service endpoints (e.g. announcements) that read
    under a well-known identity instead of an authenticated caller's. Mirrors
    `middleware.auth.get_rls_session`'s shape so a fixed identity gets the
    same `set_rls_context` call -- and the same transaction-local
    re-application guarantee -- as any authenticated request, instead of each
    endpoint hand-rolling its own `set_rls_context` call.
    """

    async def _get_fixed_identity_session() -> AsyncSession:
        global app_session_factory
        if not app_session_factory:
            await init_db()
        async with app_session_factory() as session:
            await set_rls_context(session, user_id)
            yield session

    return _get_fixed_identity_session


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
