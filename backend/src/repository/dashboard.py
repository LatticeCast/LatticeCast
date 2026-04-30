from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    @staticmethod
    def _build_params(
        param_specs: list[dict],
        runtime_params: dict[str, Any] | None,
    ) -> list:
        """Map LatticeQL param_specs to a positional values list.

        Each spec has "name" ($1, $2, ...) and "kind" (workspace_id, limit, ...).
        For kind="workspace_id", reads "workspace_id" from runtime_params.
        For other kinds, reads runtime_params[name.lstrip("$")].
        """
        bound = []
        for spec in param_specs:
            kind = spec.get("kind", "")
            name = spec.get("name", "")
            if kind == "workspace_id":
                value = runtime_params.get("workspace_id") if runtime_params else None
            else:
                key = name.lstrip("$")
                value = runtime_params.get(key) if runtime_params else None
            bound.append(value)
        return bound

    @staticmethod
    async def execute(
        session: AsyncSession,
        sql: str,
        param_specs: list[dict],
        runtime_params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a pre-compiled LatticeQL query and return rows as dicts.

        For v0.24, LatticeQL inlines workspace_id at compile time (option 1),
        so param_specs is normally empty and text(sql) is sufficient.
        _build_params is reserved for future option-2 prepared-statement support.
        """
        DashboardRepository._build_params(param_specs, runtime_params)
        result = await session.execute(text(sql))
        return [dict(row) for row in result.mappings().all()]
