from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    @staticmethod
    async def execute(
        session: AsyncSession,
        sql: str,
        param_specs: list[dict],
        runtime_params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a pre-compiled LatticeQL query and return rows as dicts.

        param_specs is always empty today: compile_lql inlines $1 itself --
        LatticeQL does not, contrary to what this docstring used to say -- and
        rejects a query that still carries $2 or higher, because the names
        behind those placeholders are not exposed by its API.
        """
        result = await session.execute(text(sql))
        return [dict(row) for row in result.mappings().all()]
