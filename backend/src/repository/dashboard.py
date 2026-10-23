from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    @staticmethod
    async def execute(
        session: AsyncSession,
        sql: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute a pre-compiled LatticeQL query and return rows as dicts.

        ``compile_lql`` resolves the LQL table name in its authorised workspace
        and supplies the resulting numeric identity as a bound value.
        """
        result = await session.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
