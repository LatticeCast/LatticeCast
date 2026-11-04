"""GET /tables keeps its full schema response with a constant query count."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from models.table_view import TableView
from router.api.tables.crud import list_tables


def _result(*, mappings=None, scalars=None):
    result = MagicMock()
    result.mappings.return_value.all.return_value = mappings or []
    result.scalars.return_value.all.return_value = scalars or []
    return result


def test_list_tables_batches_across_workspaces_and_preserves_view_order():
    workspace_a, workspace_b = uuid4(), uuid4()
    now = datetime.now(UTC)
    table_rows = [
        {
            "workspace_id": workspace_a,
            "table_id": 11,
            "table_name": "first",
            "config": {"columns": [{"column_id": "title"}], "view_order": [2, 1], "default_view": 2},
            "created_at": now,
            "updated_at": now,
        },
        {
            "workspace_id": workspace_b,
            "table_id": 12,
            "table_name": "second",
            "config": {"columns": [], "view_config": {"sort": {"colId": "title", "dir": "desc"}}},
            "created_at": now,
            "updated_at": now,
        },
    ]
    views = [
        TableView(table_id=11, view_id=1, config={"name": "Grid", "type": "table"}),
        TableView(table_id=11, view_id=2, config={"name": "Board", "type": "kanban"}),
    ]
    session = AsyncMock()
    session.execute.side_effect = [
        _result(mappings=table_rows),
        _result(scalars=views),
    ]
    with (
        patch("repository.table.reapply_rls_context", new_callable=AsyncMock),
        patch("repository.table_view.reapply_rls_context", new_callable=AsyncMock),
    ):
        response = asyncio.run(list_tables(None, session))

    assert session.execute.await_count == 2
    assert [table["table_id"] for table in response] == [11, 12]
    assert response[0]["columns"] == [{"column_id": "title"}]
    assert [view["view_id"] for view in response[0]["views"]] == [2, 1]
    assert response[0]["default_view"] == 2
    assert response[1]["views"] == []
    assert response[1]["view_config"]["sort"]["dir"] == "desc"


def test_list_tables_skips_view_query_when_no_tables_are_visible():
    session = AsyncMock()
    session.execute.return_value = _result()
    with patch("repository.table.reapply_rls_context", new_callable=AsyncMock):
        response = asyncio.run(list_tables(None, session))

    assert response == []
    assert session.execute.await_count == 1
