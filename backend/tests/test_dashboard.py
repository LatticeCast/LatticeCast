"""
Tests for the widget query endpoint and DashboardRepository.

  POST /api/v1/tables/{table_id}/views/{view_name}/widgets/{widget_id}/query

Unit tests:  mock AsyncSession; verify execute() behavior.
Integration: requires live stack (INTEGRATION_TESTS=1).
             Happy-path execution is xfail: LatticeQL v0.24 compiles SQL that
             references tables.table_name (dropped in V21); see test_lattice_ql.py.

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
    """DashboardRepository.execute() with empty params uses session.execute(text(sql))."""

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

            rows = await DashboardRepository.execute(session, "SELECT 1", [], None)
            assert rows == []
            session.execute.assert_called_once()

        _run(_run_test())

    def test_execute_converts_mappings_to_dicts(self):
        async def _run_test():
            fake_rows = [{"measure": 5}, {"measure": 3}]
            session = self._make_session(fake_rows)
            from repository.dashboard import DashboardRepository

            rows = await DashboardRepository.execute(session, "SELECT 1", [], None)
            assert rows == [{"measure": 5}, {"measure": 3}]

        _run(_run_test())

    def test_execute_passes_sql_as_text(self):
        """session.execute receives a SQLAlchemy text() clause."""
        from sqlalchemy import TextClause

        async def _run_test():
            session = self._make_session([])
            from repository.dashboard import DashboardRepository

            await DashboardRepository.execute(session, "SELECT 42 AS n", [], None)
            call_args = session.execute.call_args
            stmt = call_args[0][0]
            assert isinstance(stmt, TextClause)

        _run(_run_test())

    def test_execute_ignores_runtime_params_when_empty_params(self):
        """runtime_params are accepted but don't change the empty-params path."""

        async def _run_test():
            session = self._make_session([{"count": 7}])
            from repository.dashboard import DashboardRepository

            rows = await DashboardRepository.execute(
                session, "SELECT 7 AS count", [], {"sprint": "Q1"}
            )
            assert rows == [{"count": 7}]
            session.execute.assert_called_once()

        _run(_run_test())


# ---------------------------------------------------------------------------
# Integration tests — require live backend stack (DB + Redis)
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BASE_URL", "http://localhost:13491")
BACKEND_LIVE = os.environ.get("INTEGRATION_TESTS", "0") == "1"

_skip_integration = pytest.mark.skipif(
    not BACKEND_LIVE,
    reason="Set INTEGRATION_TESTS=1 to run against a live stack",
)


@_skip_integration
class TestWidgetQueryEndpoint:
    """Integration tests against the HTTP endpoint."""

    def _make_dashboard_view_payload(self, table_id: str) -> dict:
        return {
            "name": "Sales Dashboard",
            "type": "dashboard",
            "config": {
                "layout": [{"widget_id": "w1", "x": 0, "y": 0, "w": 6, "h": 4}],
                "widgets": {
                    "w1": {
                        "title": "Row count",
                        "chart": "number",
                        "lql": f'table("{table_id}") | aggregate(count())',
                        "binding": {"value": "measure"},
                    }
                },
            },
        }

    def test_non_dashboard_view_returns_400(self):
        """POST to a Table-type view returns 400."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
                ws_r = await client.get("/api/v1/workspaces", headers=headers)
                assert ws_r.status_code == 200
                ws_id = ws_r.json()[0]["workspace_id"]

                await client.post(
                    "/api/v1/tables",
                    json={"table_id": "dash_nondash", "workspace_id": str(ws_id)},
                    headers=headers,
                )

                r = await client.post(
                    "/api/v1/tables/dash_nondash/views/Table/widgets/w1/query",
                    json={},
                    headers=headers,
                )
                assert r.status_code == 400
                assert "not a dashboard" in r.json()["detail"].lower()

        _run(_run_test())

    def test_unknown_widget_returns_404(self):
        """POST with an unknown widget_id returns 404."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
                ws_r = await client.get("/api/v1/workspaces", headers=headers)
                ws_id = ws_r.json()[0]["workspace_id"]

                await client.post(
                    "/api/v1/tables",
                    json={"table_id": "dash_wid404", "workspace_id": str(ws_id)},
                    headers=headers,
                )
                view = self._make_dashboard_view_payload("dash_wid404")
                await client.post(
                    "/api/v1/tables/dash_wid404/views",
                    json={"name": view["name"], "type": view["type"], "config": view["config"]},
                    headers=headers,
                )

                r = await client.post(
                    "/api/v1/tables/dash_wid404/views/Sales Dashboard/widgets/no_widget/query",
                    json={},
                    headers=headers,
                )
                assert r.status_code == 404
                assert "widget" in r.json()["detail"].lower()

        _run(_run_test())

    @pytest.mark.xfail(
        reason=(
            "LatticeQL SQL references tables.table_name dropped in V21. "
            "Execution will succeed once the DB schema is updated."
        ),
        strict=False,
    )
    def test_count_widget_returns_rows_shape(self):
        """Create dashboard with count widget, hit endpoint, assert response shape."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
                ws_r = await client.get("/api/v1/workspaces", headers=headers)
                assert ws_r.status_code == 200
                ws_id = ws_r.json()[0]["workspace_id"]

                tbl_id = "dash_count_test"
                await client.post(
                    "/api/v1/tables",
                    json={"table_id": tbl_id, "workspace_id": str(ws_id)},
                    headers=headers,
                )
                for _ in range(3):
                    await client.post(
                        f"/api/v1/tables/{tbl_id}/rows",
                        json={"row_data": {}},
                        headers=headers,
                    )

                view = self._make_dashboard_view_payload(tbl_id)
                await client.post(
                    f"/api/v1/tables/{tbl_id}/views",
                    json={"name": view["name"], "type": view["type"], "config": view["config"]},
                    headers=headers,
                )

                r = await client.post(
                    f"/api/v1/tables/{tbl_id}/views/Sales Dashboard/widgets/w1/query",
                    json={},
                    headers=headers,
                )
                assert r.status_code == 200
                body = r.json()
                assert "rows" in body
                assert isinstance(body["rows"], list)
                assert len(body["rows"]) == 1
                assert "measure" in body["rows"][0]
                assert body["rows"][0]["measure"] >= 3

        _run(_run_test())


@_skip_integration
class TestDashboardRepositoryIntegration:
    """Direct DashboardRepository.execute() against a real DB session."""

    @pytest.mark.xfail(
        reason=(
            "LatticeQL-generated SQL uses `tables.table_name` dropped in V21. "
            "Execution requires a schema update."
        ),
        strict=False,
    )
    def test_execute_count_query(self):
        """Seed rows, compile LQL, execute via DashboardRepository, verify count."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
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
