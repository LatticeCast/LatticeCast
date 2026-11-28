"""
Tests for config/lattice_ql.py — schema cache + compile helper.

Unit test:    mock the PG cache + table schema reads; assert the backend binds
              its authorised workspace to compiler output.
Execution against a real database is covered by e2e (e2e/tables/test_lql_*.py).

Run inside Docker:
    docker compose exec -T backend sh -lc \
      'cd /app && PYTHONPATH=/app/src .venv/bin/python -m pytest tests/test_lattice_ql.py -v'
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.lattice_ql import compile_lql, invalidate_schema_cache

# ---------------------------------------------------------------------------
# Unit tests (no live services required)
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


class TestCompileLql:
    """Unit tests — all external calls mocked."""

    def _make_table(self, name: str, col_name: str = "status", col_type: str = "select") -> MagicMock:
        table = MagicMock()
        table.table_id = 101
        table.table_name = name
        table.workspace_id = "ws-uuid-0001"
        table.columns = [{"name": col_name, "column_id": "col-001", "type": col_type}]
        return table

    def test_compile_lql_returns_tuple(self):
        """compile_lql(lql, workspace_id, session) returns (sql, params: dict)."""

        async def _run_test():
            # Arrange: cache returns a miss, TableRepository returns one table
            fake_table = self._make_table("Tasks")

            session_mock = MagicMock()

            with (
                patch("config.lattice_ql.cache_get", AsyncMock(return_value=None)),
                patch("config.lattice_ql.cache_set", AsyncMock()),
                patch("config.lattice_ql.TableRepository") as MockRepo,
                patch("config.lattice_ql.TableViewRepository") as MockViewRepo,
            ):
                instance = MockRepo.return_value
                instance.list_by_workspace = AsyncMock(return_value=[fake_table])
                MockViewRepo.return_value.get_tables_schema = AsyncMock(
                    return_value={"columns": fake_table.columns}
                )

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
            assert params == {"workspace_id": "00000000-0000-0000-0000-000000000001"}
            assert "table_name = 'Tasks'" in sql
            assert ":table_name" not in sql
            assert "workspace_id = CAST(:workspace_id AS uuid)" in sql

        _run(_run_test())

    def test_compile_lql_uses_cache(self):
        """If the PG cache has a cached schema, TableRepository is never called."""

        async def _run_test():
            cached_schema = {
                "Tasks": {
                    "columns": {"status": {"id": "col-001", "type": "select"}},
                }
            }

            session_mock = MagicMock()

            with (
                patch("config.lattice_ql.cache_get", AsyncMock(return_value=cached_schema)),
                patch("config.lattice_ql.cache_set", AsyncMock()),
                patch("config.lattice_ql.TableRepository") as MockRepo,
            ):
                instance = MockRepo.return_value
                instance.list_by_workspace = AsyncMock(return_value=[])

                result = await compile_lql(
                    'table("Tasks") | aggregate(count())',
                    "00000000-0000-0000-0000-000000000001",
                    session_mock,
                )

            # TableRepository should NOT have been queried (schema from cache)
            instance.list_by_workspace.assert_not_called()
            sql, params = result
            assert isinstance(sql, str) and sql.strip()
            assert params == {"workspace_id": "00000000-0000-0000-0000-000000000001"}
            assert "table_name = 'Tasks'" in sql

        _run(_run_test())

    def test_compile_lql_raises_value_error_on_bad_lql(self):
        """LatticeQLError is converted to ValueError with kind:message."""

        async def _run_test():
            cached_schema = {"Tasks": {"columns": {}}}

            session_mock = MagicMock()

            with patch("config.lattice_ql.cache_get", AsyncMock(return_value=cached_schema)):
                with pytest.raises(ValueError):
                    await compile_lql("this is not valid lql !!!!", "ws-id", session_mock)

        _run(_run_test())

    def test_invalidate_schema_cache_deletes_key(self):
        """invalidate_schema_cache deletes the correct cache key."""

        async def _run_test():
            with patch("config.lattice_ql.cache_delete", AsyncMock()) as cache_delete_mock:
                await invalidate_schema_cache("my-workspace-id")

            cache_delete_mock.assert_called_once_with("lql:schema:my-workspace-id")

        _run(_run_test())

