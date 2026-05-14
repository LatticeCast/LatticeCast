"""
Unit tests verifying that all remaining session.refresh() call sites operate on
attached ORM instances (not detached), so they cannot raise
"Could not refresh instance <...> because this instance is not associated with this Session".

Contrast with test_table_view_repo.py which verifies detached-safe paths do NOT
call session.refresh() at all. Here every path SHOULD call refresh — the point is
to document and protect the attachment invariant for each method.

Run inside Docker:
    docker compose exec -T backend python -m pytest tests/test_session_refresh_attached.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4


def _run(coro):
    return asyncio.run(coro)


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    """Minimal async session mock: add/commit/refresh are no-ops."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ── WorkspaceRepository ───────────────────────────────────────────────────────


class TestWorkspaceRepositoryCreate:
    def test_refresh_called_once_after_commit(self):
        """create() adds workspace to session, commits, then refreshes — attached."""

        async def _run_test():
            from repository.workspace import WorkspaceRepository

            session = _make_session()
            repo = WorkspaceRepository(session)
            workspace = await repo.create("my-workspace")
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(workspace)

        _run(_run_test())

    def test_add_called_before_refresh(self):
        """session.add() must precede refresh so the instance is attached."""

        async def _run_test():
            from repository.workspace import WorkspaceRepository

            session = _make_session()
            call_order: list[str] = []
            session.add.side_effect = lambda _: call_order.append("add")
            session.commit.side_effect = lambda: call_order.append("commit") or asyncio.coroutine(lambda: None)()
            session.commit = AsyncMock(side_effect=lambda: call_order.append("commit"))
            session.refresh = AsyncMock(side_effect=lambda _: call_order.append("refresh"))
            repo = WorkspaceRepository(session)
            await repo.create("ws")
            assert call_order == ["add", "commit", "refresh"]

        _run(_run_test())


class TestWorkspaceRepositoryAddMember:
    def test_refresh_called_once_after_commit(self):
        """add_member() adds WorkspaceMember to session, commits, then refreshes — attached."""

        async def _run_test():
            from repository.workspace import WorkspaceRepository

            session = _make_session()
            repo = WorkspaceRepository(session)
            member = await repo.add_member(uuid4(), uuid4(), role="member")
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(member)

        _run(_run_test())


class TestWorkspaceRepositoryUpdateMemberRole:
    def test_refresh_called_on_orm_loaded_member(self):
        """update_member_role() loads member via ORM select then refreshes — attached."""

        async def _run_test():
            from models.workspace import WorkspaceMember
            from repository.workspace import WorkspaceRepository

            workspace_id = uuid4()
            user_id = uuid4()
            existing_member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")

            session = _make_session()
            scalar_result = MagicMock()
            scalar_result.scalar_one_or_none.return_value = existing_member
            session.execute = AsyncMock(return_value=scalar_result)

            repo = WorkspaceRepository(session)
            result = await repo.update_member_role(workspace_id, user_id, "owner")

            assert result is not None
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(existing_member)

        _run(_run_test())

    def test_returns_none_when_member_not_found(self):
        """update_member_role() returns None without calling refresh if member missing."""

        async def _run_test():
            from repository.workspace import WorkspaceRepository

            session = _make_session()
            scalar_result = MagicMock()
            scalar_result.scalar_one_or_none.return_value = None
            session.execute = AsyncMock(return_value=scalar_result)

            repo = WorkspaceRepository(session)
            result = await repo.update_member_role(uuid4(), uuid4(), "owner")

            assert result is None
            session.refresh.assert_not_called()

        _run(_run_test())


# ── TableRepository ───────────────────────────────────────────────────────────


class TestTableRepositoryCreate:
    def test_refresh_called_once_after_commit(self):
        """create() adds Table to session, commits, then refreshes — attached."""

        async def _run_test():
            from repository.table import TableRepository

            session = _make_session()
            repo = TableRepository(session)
            table = await repo.create(uuid4(), "my-table")
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(table)

        _run(_run_test())


class TestTableRepositoryUpdate:
    def test_refresh_called_on_orm_loaded_table(self):
        """update() takes an ORM-loaded table, modifies, commits, then refreshes — attached."""

        async def _run_test():
            from models.table import Table
            from repository.table import TableRepository

            workspace_id = uuid4()
            table = Table(workspace_id=workspace_id, table_id="old-name")

            session = _make_session()
            repo = TableRepository(session)
            result = await repo.update(table, "new-name")

            assert result.table_id == "new-name"
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(table)

        _run(_run_test())


# ── UserRepository ────────────────────────────────────────────────────────────


class TestUserRepositoryUpdate:
    def test_refresh_called_on_orm_loaded_user(self):
        """update() takes an ORM-loaded user, modifies, commits, then refreshes — attached."""

        async def _run_test():
            from models.user import User
            from repository.user import UserRepository

            user = User(role="user")

            session = _make_session()
            repo = UserRepository(session)
            result = await repo.update(user, role="admin")

            assert result.role == "admin"
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(user)

        _run(_run_test())


# ── GdprRepository ────────────────────────────────────────────────────────────


class TestGdprRepositoryUpdateEmail:
    def test_refresh_called_on_orm_loaded_gdpr(self):
        """update_email() loads gdpr via ORM select, modifies, commits, then refreshes — attached."""

        async def _run_test():
            from models.user import Gdpr
            from repository.user import GdprRepository

            user_id = uuid4()
            existing_gdpr = Gdpr(user_id=user_id, email="old@example.com")

            session = _make_session()

            # First execute: get_by_email(new_email) → None (no conflict)
            # Second execute: get_by_user_id(user_id) → existing_gdpr
            no_conflict = MagicMock()
            no_conflict.scalar_one_or_none.return_value = None
            has_gdpr = MagicMock()
            has_gdpr.scalar_one_or_none.return_value = existing_gdpr
            session.execute = AsyncMock(side_effect=[no_conflict, has_gdpr])

            repo = GdprRepository(session)
            result = await repo.update_email(user_id, "new@example.com")

            assert result.email == "new@example.com"
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(existing_gdpr)

        _run(_run_test())


# ── RowRepository ─────────────────────────────────────────────────────────────


class TestRowRepositoryUpdate:
    def test_refresh_called_on_orm_loaded_row(self):
        """update() takes an ORM-loaded row (from get_by_number), commits, then refreshes — attached."""

        async def _run_test():
            from models.row import Row, RowUpdate
            from repository.row import RowRepository

            workspace_id = uuid4()
            row = Row(
                workspace_id=workspace_id,
                table_id="my-table",
                row_id=1,
                row_data={"title": "old"},
            )

            session = _make_session()
            repo = RowRepository(session)
            update = RowUpdate(row_data={"title": "new"})
            result = await repo.update(row=row, data=update, updated_by=uuid4())

            assert result.row_data["title"] == "new"
            session.commit.assert_called_once()
            session.refresh.assert_called_once()
            assert session.refresh.call_args == call(row)

        _run(_run_test())

    def test_create_does_not_call_refresh(self):
        """create() uses raw INSERT+RETURNING (PG trigger sets row_id) — must NOT call refresh."""

        async def _run_test():
            from repository.row import RowRepository

            workspace_id = uuid4()
            now = datetime.utcnow()

            fake_row = {
                "workspace_id": workspace_id,
                "table_id": "my-table",
                "row_id": 42,
                "row_data": {},
                "created_by": None,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
            mapping_result = MagicMock()
            mapping_result.mappings.return_value.one.return_value = fake_row

            session = _make_session()
            session.execute = AsyncMock(return_value=mapping_result)

            repo = RowRepository(session)
            result = await repo.create(workspace_id=workspace_id, table_id="my-table")

            # The 2024 fix: raw INSERT, no session.refresh()
            session.refresh.assert_not_called()
            assert result.row_id == 42

        _run(_run_test())
