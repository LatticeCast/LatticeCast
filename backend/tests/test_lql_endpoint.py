"""Workspace-scoped LQL endpoint contract."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from router.api.lql import LQLRequest, query_workspace_lql, router

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000123")


class TestWorkspaceLQL(unittest.TestCase):
    def test_route_is_registered(self):
        self.assertTrue(
            any(route.path == "/workspaces/{workspace_id}/lql" and "POST" in route.methods for route in router.routes)
        )

    def test_body_compiles_in_selected_workspace(self):
        session = AsyncMock()
        workspace = SimpleNamespace(workspace_id=WORKSPACE_ID)
        with (
            patch("router.api.lql.WorkspaceRepository") as repository,
            patch("router.api.lql.compile_lql", new_callable=AsyncMock) as compile_lql,
            patch("router.api.lql.DashboardRepository.execute", new_callable=AsyncMock) as execute,
        ):
            repository.return_value.get_by_id = AsyncMock(return_value=workspace)
            compile_lql.return_value = ("SELECT 1", {"workspace_id": str(WORKSPACE_ID)})
            execute.return_value = [{"measure": 1}]

            result = asyncio.run(
                query_workspace_lql(
                    WORKSPACE_ID,
                    LQLRequest(lql='table("Tasks") | aggregate(count())'),
                    None,
                    session,
                )
            )

            repository.return_value.get_by_id.assert_awaited_once_with(WORKSPACE_ID)
            compile_lql.assert_awaited_once_with('table("Tasks") | aggregate(count())', str(WORKSPACE_ID), session)
            execute.assert_awaited_once_with(session, "SELECT 1", {"workspace_id": str(WORKSPACE_ID)})
            self.assertEqual(result, {"rows": [{"measure": 1}]})

    def test_unreadable_workspace_does_not_compile(self):
        session = AsyncMock()
        with (
            patch("router.api.lql.WorkspaceRepository") as repository,
            patch("router.api.lql.compile_lql", new_callable=AsyncMock) as compile_lql,
        ):
            repository.return_value.get_by_id = AsyncMock(return_value=None)
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(query_workspace_lql(WORKSPACE_ID, LQLRequest(lql='table("Tasks")'), None, session))
            self.assertEqual(raised.exception.status_code, 404)
            compile_lql.assert_not_awaited()

    def test_invalid_lql_returns_bad_request(self):
        session = AsyncMock()
        with (
            patch("router.api.lql.WorkspaceRepository") as repository,
            patch("router.api.lql.compile_lql", new_callable=AsyncMock) as compile_lql,
        ):
            repository.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(workspace_id=WORKSPACE_ID))
            compile_lql.side_effect = ValueError("invalid LQL")
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(query_workspace_lql(WORKSPACE_ID, LQLRequest(lql="bad"), None, session))
            self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
