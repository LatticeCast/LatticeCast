"""
Tests for config/lattice_ql.py — schema cache + compile helper.

Unit test:    mock Redis + TableRepository; assert compile_lql returns (sql, params).
Integration:  real workspace + table; verify schema shape and compile output.
              Execution via asyncpg is marked xfail: the SQL LatticeQL generates
              references `tables.table_name` which was dropped in migration V21.
              Full execution requires a DB schema update (future work).

Run inside Docker:
    docker compose exec -T backend python -m pytest tests/test_lattice_ql.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Unit tests (no live services required)
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


class TestCompileLql:
    """Unit tests — all external calls mocked."""

    def _make_table(self, name: str, col_name: str = "status", col_type: str = "select") -> MagicMock:
        table = MagicMock()
        table.table_id = name
        table.workspace_id = "ws-uuid-0001"
        table.columns = [{"name": col_name, "column_id": "col-001", "type": col_type}]
        return table

    def test_compile_lql_returns_tuple(self):
        """compile_lql(lql, workspace_id, session) returns (sql: str, params: list)."""

        async def _run_test():
            # Arrange: Redis returns cache-miss, TableRepository returns one table
            redis_mock = AsyncMock()
            redis_mock.get = AsyncMock(return_value=None)
            redis_mock.setex = AsyncMock()

            fake_table = self._make_table("Tasks")

            session_mock = MagicMock()

            with patch("config.lattice_ql.get_redis", AsyncMock(return_value=redis_mock)):
                with patch("config.lattice_ql.TableRepository") as MockRepo:
                    instance = MockRepo.return_value
                    instance.list_by_workspace = AsyncMock(return_value=[fake_table])

                    from config.lattice_ql import compile_lql

                    result = await compile_lql(
                        'table("Tasks") | aggregate(count())',
                        "00000000-0000-0000-0000-000000000001",
                        session_mock,
                    )

            # Assert
            assert isinstance(result, tuple), "compile_lql must return a tuple"
            assert len(result) == 2, "tuple must have exactly 2 elements (sql, params)"
            sql, params = result
            assert isinstance(sql, str) and sql.strip(), "sql must be a non-empty string"
            assert isinstance(params, (list, tuple)), "params must be a list or tuple"

        _run(_run_test())

    def test_compile_lql_uses_cache(self):
        """If Redis has a cached schema, TableRepository is never called."""

        async def _run_test():
            cached_schema = json.dumps(
                {
                    "Tasks": {
                        "table_id": "tasks-tbl",
                        "columns": {"status": {"id": "col-001", "type": "select"}},
                    }
                }
            )
            redis_mock = AsyncMock()
            redis_mock.get = AsyncMock(return_value=cached_schema)
            redis_mock.setex = AsyncMock()

            session_mock = MagicMock()

            with patch("config.lattice_ql.get_redis", AsyncMock(return_value=redis_mock)):
                with patch("config.lattice_ql.TableRepository") as MockRepo:
                    instance = MockRepo.return_value
                    instance.list_by_workspace = AsyncMock(return_value=[])

                    from config.lattice_ql import compile_lql

                    result = await compile_lql(
                        'table("Tasks") | aggregate(count())',
                        "00000000-0000-0000-0000-000000000001",
                        session_mock,
                    )

            # TableRepository should NOT have been queried (schema from cache)
            instance.list_by_workspace.assert_not_called()
            sql, params = result
            assert isinstance(sql, str) and sql.strip()

        _run(_run_test())

    def test_compile_lql_raises_value_error_on_bad_lql(self):
        """LatticeQLError is converted to ValueError with kind:message."""

        async def _run_test():
            cached_schema = json.dumps({"Tasks": {"table_id": "t", "columns": {}}})
            redis_mock = AsyncMock()
            redis_mock.get = AsyncMock(return_value=cached_schema)

            session_mock = MagicMock()

            with patch("config.lattice_ql.get_redis", AsyncMock(return_value=redis_mock)):
                from config.lattice_ql import compile_lql

                with pytest.raises(ValueError):
                    await compile_lql("this is not valid lql !!!!", "ws-id", session_mock)

        _run(_run_test())

    def test_invalidate_schema_cache_deletes_key(self):
        """invalidate_schema_cache deletes the correct Valkey key."""

        async def _run_test():
            redis_mock = AsyncMock()
            redis_mock.delete = AsyncMock()

            with patch("config.lattice_ql.get_redis", AsyncMock(return_value=redis_mock)):
                from config.lattice_ql import invalidate_schema_cache

                await invalidate_schema_cache("my-workspace-id")

            redis_mock.delete.assert_called_once_with("lql:schema:my-workspace-id")

        _run(_run_test())


# ---------------------------------------------------------------------------
# Integration tests (require live backend stack: DB + Redis)
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BASE_URL", "http://localhost:13491")
BACKEND_LIVE = os.environ.get("INTEGRATION_TESTS", "0") == "1"

_skip_integration = pytest.mark.skipif(
    not BACKEND_LIVE,
    reason="Set INTEGRATION_TESTS=1 to run against a live stack",
)


@_skip_integration
class TestCompileLqlIntegration:
    """Integration tests — require `docker compose up` with dev stack running."""

    def test_get_schema_reflects_real_table(self):
        """Creating a table then calling get_schema returns its columns in the schema dict."""
        import httpx

        async def _run_test():
            # Create a workspace + table via API (AUTH_REQUIRED=false, bearer = user_name)
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}

                # Get existing workspace
                r = await client.get("/api/v1/workspaces", headers=headers)
                assert r.status_code == 200
                workspaces = r.json()
                assert workspaces, "No workspaces found — bootstrap dev user first"
                ws_id = workspaces[0]["workspace_id"]

                # Create a test table
                r = await client.post(
                    "/api/v1/tables",
                    json={"table_id": "lql_test_schema", "workspace_id": str(ws_id)},
                    headers=headers,
                )
                # 409 means it already exists from a previous run — that's fine
                assert r.status_code in (201, 409), f"Unexpected: {r.status_code} {r.text}"

                # Fetch the schema via the helper
                # We re-import to get a fresh module state inside Docker
                sys.path.insert(0, "/app/src")
                from config.db import app_session_factory  # type: ignore[import]

                from config.lattice_ql import get_schema  # noqa: E402

                async with app_session_factory() as session:
                    schema = await get_schema(str(ws_id), session)

                assert "lql_test_schema" in schema, f"Table not found in schema keys: {list(schema.keys())}"
                entry = schema["lql_test_schema"]
                assert "columns" in entry
                # Default template adds Doc, Title, Description columns
                assert "Doc" in entry["columns"] or "Title" in entry["columns"]

        _run(_run_test())

    def test_compile_lql_returns_sql_and_params(self):
        """compile_lql against a real table returns (sql, params) without error."""
        import httpx

        async def _run_test():
            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
                r = await client.get("/api/v1/workspaces", headers=headers)
                ws_id = r.json()[0]["workspace_id"]

            sys.path.insert(0, "/app/src")
            from config.db import app_session_factory  # type: ignore[import]

            from config.lattice_ql import compile_lql

            async with app_session_factory() as session:
                sql, params = await compile_lql(
                    'table("lql_test_schema") | aggregate(count())',
                    str(ws_id),
                    session,
                )

            assert isinstance(sql, str) and sql.strip()
            assert isinstance(params, (list, tuple))

        _run(_run_test())

    @pytest.mark.xfail(
        reason=(
            "LatticeQL-generated SQL uses `tables.table_name` (V21 dropped that column). "
            "Full execution requires a DB schema update to re-add table_name as an alias."
        ),
        strict=False,
    )
    def test_execute_count_query(self):
        """Execute compiled count query via asyncpg and verify row count."""
        import httpx

        async def _run_test():
            import asyncpg

            async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
                headers = {"Authorization": "Bearer lattice"}
                ws_r = await client.get("/api/v1/workspaces", headers=headers)
                ws_id = ws_r.json()[0]["workspace_id"]

                # Insert 2 rows so count is predictable
                for _ in range(2):
                    await client.post(
                        "/api/v1/tables/lql_test_schema/rows",
                        json={"row_data": {}},
                        headers=headers,
                    )

            sys.path.insert(0, "/app/src")
            from config.db import app_session_factory  # type: ignore[import]

            from config.lattice_ql import compile_lql

            async with app_session_factory() as session:
                sql, params = await compile_lql(
                    'table("lql_test_schema") | aggregate(count())',
                    str(ws_id),
                    session,
                )

            # Execute via asyncpg using app_user credentials from env
            db_url = os.environ.get(
                "APP_DB_URL",
                "postgresql://app_user:app_password@db:5432/db",
            )
            conn = await asyncpg.connect(db_url)
            try:
                rows = await conn.fetch(sql, *([ws_id] + list(params)))
                count = rows[0]["measure"]
                assert count >= 2
            finally:
                await conn.close()

        _run(_run_test())
