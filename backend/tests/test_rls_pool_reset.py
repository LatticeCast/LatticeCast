"""The RLS identity must not survive a pooled connection.

`app.current_user_id` is a session-level GUC and SQLAlchemy's asyncpg pool
returns a connection with only a ROLLBACK -- it never issues DISCARD/RESET.
Without the checkout hook in core.db, a request that does not set an identity
(the pre-token lookups, or any route that forgets get_rls_session) would be
authorised as whoever used that connection last: a cross-user read.

These tests pin the hook's contract. The last one needs a database and skips
when none is reachable; it is the behaviour the hook exists for, so it must run
wherever the backend talks to PostgreSQL.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import core.db as core_db
from core.db import (
    RLS_IDENTITY_SETTING,
    clear_rls_identity,
    install_rls_identity_hook,
    install_rls_reset_hook,
    set_rls_context,
)


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.closed = False

    def execute(self, statement, *args) -> None:
        self.executed.append((statement, args))

    def close(self) -> None:
        self.closed = True


class _FakeDatabaseConnection:
    def __init__(self) -> None:
        self.cursors: list[_FakeCursor] = []

    def cursor(self) -> _FakeCursor:
        cursor = _FakeCursor()
        self.cursors.append(cursor)
        return cursor


def test_clear_rls_identity_empties_the_setting_and_closes_the_cursor():
    connection = _FakeDatabaseConnection()

    clear_rls_identity(connection)

    assert len(connection.cursors) == 1
    cursor = connection.cursors[0]
    assert cursor.closed is True
    assert len(cursor.executed) == 1
    statement, args = cursor.executed[0]
    assert " ".join(statement.split()) == f"SELECT set_config('{RLS_IDENTITY_SETTING}', '', false)"
    assert args == ()


def test_clear_rls_identity_is_fail_closed():
    """A connection whose reset fails must not be handed to a caller."""

    class _Broken(_FakeDatabaseConnection):
        def cursor(self):
            raise RuntimeError("server closed the connection")

    with pytest.raises(RuntimeError, match="server closed the connection"):
        clear_rls_identity(_Broken())


def test_install_rls_reset_hook_is_idempotent(monkeypatch):
    engine = create_async_engine("postgresql+asyncpg://user:pass@127.0.0.1:1/db")
    registered: list[tuple[str, object]] = []
    real_listen = event.listen

    def counting_listen(target, identifier, fn, *args, **kwargs):
        registered.append((identifier, fn))
        return real_listen(target, identifier, fn, *args, **kwargs)

    monkeypatch.setattr(core_db.event, "listen", counting_listen)
    try:
        install_rls_reset_hook(engine)
        install_rls_reset_hook(engine)
    finally:
        monkeypatch.undo()
        asyncio.run(engine.dispose())

    assert registered == [("checkout", clear_rls_identity)]
    assert event.contains(engine.sync_engine, "checkout", clear_rls_identity)


def _database_url() -> str:
    from config.settings import settings

    return settings.database.app_async_url


def _database_reachable(url: str) -> bool:
    async def probe() -> None:
        engine = create_async_engine(url, pool_size=1, max_overflow=0)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(probe())
    except Exception:
        return False
    return True


def test_pooled_connection_never_hands_over_a_previous_identity():
    url = _database_url()
    if not _database_reachable(url):
        pytest.skip("no database reachable from this environment")

    async def scenario() -> str | None:
        # One connection, so the second session must reuse the first's.
        engine = create_async_engine(url, pool_size=1, max_overflow=0)
        install_rls_reset_hook(engine)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await set_rls_context(session, str(uuid.uuid4()))
                await session.commit()

            async with maker() as session:
                result = await session.execute(text(f"SELECT current_setting('{RLS_IDENTITY_SETTING}', true)"))
                return result.scalar()
        finally:
            await engine.dispose()

    leftover = asyncio.run(scenario())
    assert leftover in (None, ""), f"pooled connection kept the previous RLS identity: {leftover!r}"


def test_install_rls_identity_hook_is_idempotent(monkeypatch):
    from sqlalchemy.orm import Session

    registered: list[tuple[str, object]] = []
    real_listen = event.listen

    def counting_listen(target, identifier, fn, *args, **kwargs):
        registered.append((identifier, fn))
        return real_listen(target, identifier, fn, *args, **kwargs)

    monkeypatch.setattr(core_db.event, "listen", counting_listen)
    try:
        install_rls_identity_hook()
        install_rls_identity_hook()
    finally:
        monkeypatch.undo()

    assert registered == [("after_begin", core_db.apply_rls_identity)]
    assert event.contains(Session, "after_begin", core_db.apply_rls_identity)


def test_identity_is_reapplied_after_a_commit():
    """A commit returns the connection; the next statement must keep its caller."""
    url = _database_url()
    if not _database_reachable(url):
        pytest.skip("no database reachable from this environment")

    async def scenario() -> tuple[str | None, str | None]:
        engine = create_async_engine(url, pool_size=1, max_overflow=0)
        install_rls_reset_hook(engine)
        install_rls_identity_hook()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        user_id = str(uuid.uuid4())
        try:
            async with maker() as session:
                await set_rls_context(session, user_id)
                await session.commit()  # ends the transaction on this connection
                result = await session.execute(
                    text(f"SELECT current_setting('{RLS_IDENTITY_SETTING}', true)")
                )
                return user_id, result.scalar()
        finally:
            await engine.dispose()

    expected, actual = asyncio.run(scenario())
    assert actual == expected, f"identity lost at the commit boundary: {actual!r}"


def test_a_session_without_identity_sets_nothing():
    url = _database_url()
    if not _database_reachable(url):
        pytest.skip("no database reachable from this environment")

    async def scenario() -> str | None:
        engine = create_async_engine(url, pool_size=1, max_overflow=0)
        install_rls_reset_hook(engine)
        install_rls_identity_hook()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                result = await session.execute(
                    text(f"SELECT current_setting('{RLS_IDENTITY_SETTING}', true)")
                )
                return result.scalar()
        finally:
            await engine.dispose()

    assert asyncio.run(scenario()) in (None, "")
