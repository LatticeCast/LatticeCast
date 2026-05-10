"""
Unit tests for TableViewRepository.update().

Verifies that update() uses raw SQL (no session.refresh()) so it works
even when the view instance is detached from the session — the root cause
of the create-view / create-PM-template 500s (task-252).

Run inside Docker:
    docker compose exec -T backend python -m pytest tests/test_table_view_repo.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

WORKSPACE_ID = uuid4()
TABLE_ID = "test_table"
VIEW_NAME = "__order__"


def _run(coro):
    return asyncio.run(coro)


def _make_session(select_row: dict | None = None) -> AsyncMock:
    session = AsyncMock()

    _update_result = MagicMock()

    if select_row is None:
        select_row = {
            "workspace_id": WORKSPACE_ID,
            "table_id": TABLE_ID,
            "name": VIEW_NAME,
            "type": "order",
            "config": ["view1"],
            "is_default": False,
            "created_by": None,
            "updated_by": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    _select_result = MagicMock()
    _select_result.mappings.return_value.one.return_value = select_row

    session.execute = AsyncMock(side_effect=[_update_result, _select_result])
    session.commit = AsyncMock()
    return session


def _make_view():
    from models.table_view import TableView

    return TableView(
        workspace_id=WORKSPACE_ID,
        table_id=TABLE_ID,
        name=VIEW_NAME,
        type="order",
        config=[],
    )


class TestTableViewRepositoryUpdate:
    def test_update_does_not_call_refresh(self):
        """update() must NOT call session.refresh() — detached instances would raise."""

        async def _run_test():
            from repository.table_view import TableViewRepository

            session = _make_session()
            repo = TableViewRepository(session)
            view = _make_view()
            await repo.update(view, {"config": ["view1"], "updated_by": None})
            session.refresh.assert_not_called()

        _run(_run_test())

    def test_update_executes_twice_and_commits(self):
        """update() runs UPDATE then SELECT, with a commit in between."""

        async def _run_test():
            from repository.table_view import TableViewRepository

            session = _make_session()
            repo = TableViewRepository(session)
            view = _make_view()
            await repo.update(view, {"config": ["view1"]})
            assert session.execute.call_count == 2
            session.commit.assert_called_once()

        _run(_run_test())

    def test_update_returns_fresh_view_from_db(self):
        """update() returns a TableView built from the re-selected DB row, not the stale input."""

        async def _run_test():
            from models.table_view import TableView
            from repository.table_view import TableViewRepository

            now = datetime.utcnow()
            fresh_row = {
                "workspace_id": WORKSPACE_ID,
                "table_id": TABLE_ID,
                "name": VIEW_NAME,
                "type": "order",
                "config": ["view1", "view2"],
                "is_default": False,
                "created_by": None,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
            session = _make_session(select_row=fresh_row)
            repo = TableViewRepository(session)
            view = _make_view()
            result = await repo.update(view, {"config": ["view1", "view2"]})
            assert isinstance(result, TableView)
            assert result.config == ["view1", "view2"]
            assert result.name == VIEW_NAME

        _run(_run_test())

    def test_update_handles_name_rename(self):
        """update() with name in updates re-selects by the new name."""

        async def _run_test():
            from models.table_view import TableView
            from repository.table_view import TableViewRepository

            new_name = "Kanban"
            now = datetime.utcnow()
            fresh_row = {
                "workspace_id": WORKSPACE_ID,
                "table_id": TABLE_ID,
                "name": new_name,
                "type": "kanban",
                "config": {},
                "is_default": False,
                "created_by": None,
                "updated_by": None,
                "created_at": now,
                "updated_at": now,
            }
            session = _make_session(select_row=fresh_row)
            repo = TableViewRepository(session)
            view = _make_view()
            result = await repo.update(view, {"name": new_name, "type": "kanban"})
            assert isinstance(result, TableView)
            assert result.name == new_name

        _run(_run_test())
