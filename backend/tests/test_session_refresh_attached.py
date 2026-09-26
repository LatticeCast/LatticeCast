"""
Unit tests verifying that repository session.refresh() calls operate on attached
ORM instances (not detached), so they cannot raise
"Could not refresh instance <...> because this instance is not associated with this Session".

Raw SQL paths deliberately construct their result models from ``RETURNING`` or
function mappings and therefore must *not* call ``session.refresh()``.  This
file protects both sides of that contract.

Run inside Docker:
    docker compose exec -T backend python -m pytest tests/test_session_refresh_attached.py -v
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
            session.commit = AsyncMock(side_effect=lambda: call_order.append("commit"))
            session.refresh = AsyncMock(side_effect=lambda _: call_order.append("refresh"))
            repo = WorkspaceRepository(session)
            await repo.create("ws")
            assert call_order == ["add", "commit", "refresh"]

        _run(_run_test())


class TestWorkspaceRepositoryGrant:
    """V33: add_member()/update_member_role() were replaced by grant(), which
    calls the grant_workspace_action PG function via raw SQL — no ORM
    WorkspaceMember instance is created or loaded, so unlike the other
    repository methods in this file, it must NOT call session.refresh()."""

    def test_executes_grant_function_and_commits_without_refresh(self):
        async def _run_test():
            from repository.workspace import WorkspaceRepository

            session = _make_session()
            session.execute = AsyncMock()
            repo = WorkspaceRepository(session)
            await repo.grant(uuid4(), uuid4(), "write")

            session.execute.assert_called_once()
            session.commit.assert_called_once()
            session.refresh.assert_not_called()

        _run(_run_test())


# ── Raw SQL repositories ──────────────────────────────────────────────────────


class TestTableRepositoryCreateFromTemplate:
    def test_returns_mapping_without_refresh(self):
        """The PG template function returns a row, rather than an attached ORM object."""

        async def _run_test():
            from repository.table import TableRepository

            workspace_id = uuid4()
            created_by = uuid4()
            now = datetime.now(UTC).replace(tzinfo=None)
            mapping_result = MagicMock()
            mapping_result.mappings.return_value.one.return_value = {
                "workspace_id": workspace_id,
                "table_id": "my-table",
                "created_at": now,
                "updated_at": now,
            }
            session = _make_session()
            session.execute = AsyncMock(side_effect=[MagicMock(), mapping_result])
            repo = TableRepository(session)
            table = await repo.create_from_template(workspace_id, "My-Table", "blank", created_by)

            assert table.workspace_id == workspace_id
            assert table.table_id == "my-table"
            assert session.execute.await_count == 2
            session.commit.assert_called_once()
            session.refresh.assert_not_called()

        _run(_run_test())


class TestTableRepositoryUpdate:
    def test_returns_returning_mapping_without_refresh(self):
        """Renames use UPDATE ... RETURNING, not mutation of the passed object."""

        async def _run_test():
            from models.table import Table
            from repository.table import TableRepository

            workspace_id = uuid4()
            table = Table(workspace_id=workspace_id, table_id="old-name")
            now = datetime.now(UTC).replace(tzinfo=None)
            mapping_result = MagicMock()
            mapping_result.mappings.return_value.one_or_none.return_value = {
                "workspace_id": workspace_id,
                "table_id": "new-name",
                "created_at": now,
                "updated_at": now,
            }

            session = _make_session()
            session.execute = AsyncMock(return_value=mapping_result)
            repo = TableRepository(session)
            result = await repo.update(table, "new-name")

            assert result.table_id == "new-name"
            session.commit.assert_called_once()
            session.refresh.assert_not_called()

        _run(_run_test())


# ── User bootstrap ────────────────────────────────────────────────────────────


class TestBootstrapUser:
    def test_refreshes_the_user_added_to_login_session(self):
        """bootstrap_user creates the User in login_session before refreshing it."""

        async def _run_test():
            from repository.user import bootstrap_user

            login_session = _make_session()
            app_session = _make_session()
            result = await bootstrap_user(login_session, app_session, "person@example.com")

            login_session.commit.assert_called_once()
            login_session.refresh.assert_called_once_with(result)
            assert any(args == call(result) for args in login_session.add.call_args_list)

        _run(_run_test())


# ── RowRepository ─────────────────────────────────────────────────────────────


class TestRowRepositoryUpdate:
    def test_returns_pg_function_mapping_without_refresh(self):
        """patch_row_data returns the updated row; the input row stays detached-safe."""

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
            now = datetime.now(UTC).replace(tzinfo=None)
            mapping_result = MagicMock()
            mapping_result.mappings.return_value.one_or_none.return_value = {
                "workspace_id": workspace_id,
                "table_id": "my-table",
                "row_id": 1,
                "row_data": {"title": "new"},
                "created_by": None,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }

            session = _make_session()
            session.execute = AsyncMock(return_value=mapping_result)
            repo = RowRepository(session)
            update = RowUpdate(row_data={"title": "new"})
            result = await repo.update(row=row, data=update, updated_by=uuid4())

            assert result.row_data["title"] == "new"
            session.commit.assert_called_once()
            session.refresh.assert_not_called()

        _run(_run_test())

    def test_create_does_not_call_refresh(self):
        """create() uses raw INSERT+RETURNING (PG trigger sets row_id) — must NOT call refresh."""

        async def _run_test():
            from repository.row import RowRepository

            workspace_id = uuid4()
            now = datetime.now(UTC).replace(tzinfo=None)

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
