"""
Tests for the workspace LQL endpoint and DashboardRepository.

  POST /api/v1/workspaces/{workspace_id}/lql

Unit tests:  mock AsyncSession; verify execute() behavior.
Integration: requires live stack (INTEGRATION_TESTS=1).

Run inside Docker:
    docker compose exec -T backend python -m pytest tests/test_dashboard.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Unit tests — no live services
# ---------------------------------------------------------------------------


class TestExecute:
    """DashboardRepository.execute() binds compiler-provided query parameters."""

    def _make_session(self, rows: list[dict]) -> AsyncMock:
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)
        return session

    def test_execute_returns_empty_list(self):
        async def _run_test():
            session = self._make_session([])
            from repository.dashboard import DashboardRepository

            rows = await DashboardRepository.execute(session, "SELECT 1", {})
            assert rows == []
            session.execute.assert_called_once()

        _run(_run_test())

    def test_execute_converts_mappings_to_dicts(self):
        async def _run_test():
            fake_rows = [{"measure": 5}, {"measure": 3}]
            session = self._make_session(fake_rows)
            from repository.dashboard import DashboardRepository

            rows = await DashboardRepository.execute(session, "SELECT 1", {})
            assert rows == [{"measure": 5}, {"measure": 3}]

        _run(_run_test())

    def test_execute_passes_sql_as_text(self):
        """session.execute receives a SQLAlchemy text() clause."""
        from sqlalchemy import TextClause

        async def _run_test():
            session = self._make_session([])
            from repository.dashboard import DashboardRepository

            await DashboardRepository.execute(session, "SELECT 42 AS n", {})
            call_args = session.execute.call_args
            stmt = call_args[0][0]
            assert isinstance(stmt, TextClause)

        _run(_run_test())

    def test_execute_passes_compiler_params(self):
        """The workspace/table-name bindings reach SQLAlchemy unchanged."""

        async def _run_test():
            session = self._make_session([{"count": 7}])
            from repository.dashboard import DashboardRepository

            params = {
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "table_name": "Tasks",
            }
            rows = await DashboardRepository.execute(session, "SELECT 7 AS count", params)
            assert rows == [{"count": 7}]
            session.execute.assert_called_once()
            assert session.execute.call_args.args[1] == params

        _run(_run_test())


# ---------------------------------------------------------------------------
# Integration tests — require live backend stack (DB)
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BASE_URL", "http://localhost:13491")
BACKEND_LIVE = os.environ.get("INTEGRATION_TESTS", "0") == "1"

_skip_integration = pytest.mark.skipif(
    not BACKEND_LIVE,
    reason="Set INTEGRATION_TESTS=1 to run against a live stack",
)


async def _lattice_auth_headers(client) -> dict:
    """Password login as the dev seed user, return Bearer headers with a signed JWT."""
    resp = await client.post(
        "/api/v1/login/password",
        json={"user_name": "lattice", "password": ""},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@_skip_integration
class TestWorkspaceLQLEndpoint:
    """Integration tests for the workspace-scoped HTTP API."""

    def test_unreadable_workspace_returns_404(self):
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = await _lattice_auth_headers(client)
                response = await client.post(
                    "/api/v1/workspaces/00000000-0000-0000-0000-000000000123/lql",
                    json={"lql": 'table("Tasks")'},
                    headers=headers,
                )
                assert response.status_code == 404

        _run(_run_test())

    def test_invalid_lql_returns_400(self):
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = await _lattice_auth_headers(client)
                workspaces = await client.get("/api/v1/workspaces", headers=headers)
                assert workspaces.status_code == 200
                workspace_id = workspaces.json()[0]["workspace_id"]

                response = await client.post(
                    f"/api/v1/workspaces/{workspace_id}/lql",
                    json={"lql": "this is not valid lql !!!!"},
                    headers=headers,
                )
                assert response.status_code == 400

        _run(_run_test())

    def test_query_can_name_any_table_in_workspace(self):
        import json

        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = await _lattice_auth_headers(client)
                tables = await client.get("/api/v1/tables", headers=headers)
                assert tables.status_code == 200
                assert tables.json(), "Seed data must provide a readable table"
                table = tables.json()[0]
                workspace_id = table["workspace_id"]
                lql = f"table({json.dumps(table['table_name'])}) | aggregate(count())"

                response = await client.post(
                    f"/api/v1/workspaces/{workspace_id}/lql",
                    json={"lql": lql},
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                assert isinstance(response.json()["rows"], list)

        _run(_run_test())


@_skip_integration
class TestDashboardRepositoryIntegration:
    """Direct DashboardRepository.execute() against a real DB session."""

    @pytest.mark.xfail(
        reason=("LatticeQL-generated SQL uses `tables.table_name` dropped in V21. Execution requires a schema update."),
        strict=False,
    )
    def test_execute_count_query(self):
        """Seed rows, compile LQL, execute via DashboardRepository, verify count."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = await _lattice_auth_headers(client)
                r = await client.get("/api/v1/workspaces", headers=headers)
                assert r.status_code == 200
                ws_id = r.json()[0]["workspace_id"]

                await client.post(
                    "/api/v1/tables",
                    json={"table_id": "dash_repo_test", "workspace_id": str(ws_id)},
                    headers=headers,
                )
                for _ in range(3):
                    await client.post(
                        "/api/v1/tables/dash_repo_test/rows",
                        json={"row_data": {}},
                        headers=headers,
                    )

            sys.path.insert(0, "/app/src")
            from config.db import app_session_factory  # type: ignore[import]

            from config.lattice_ql import compile_lql
            from repository.dashboard import DashboardRepository

            async with app_session_factory() as session:
                sql, params = await compile_lql(
                    'table("dash_repo_test") | aggregate(count())',
                    str(ws_id),
                    session,
                )
                rows = await DashboardRepository.execute(session, sql, params, None)

            assert len(rows) == 1, f"Expected 1 aggregate row, got {rows}"
            assert rows[0].get("measure") is not None

        _run(_run_test())
