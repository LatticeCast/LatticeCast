from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from lattice_ql import LatticeQLError
from lattice_ql import compile as _compile

from config.redis import get_redis
from repository.table import TableRepository

_SCHEMA_TTL = 60  # seconds


async def _build_schema(workspace_id: str, session: Any) -> dict[str, Any]:
    repo = TableRepository(session)
    tables = await repo.list_by_workspace(UUID(workspace_id))
    return {
        t.table_id: {
            "table_id": t.table_id,
            "columns": {
                c["name"].lower().replace(" ", "_"): {"id": c["column_id"], "type": c["type"]}
                for c in (t.columns or [])
                if "name" in c and "column_id" in c and "type" in c
            },
        }
        for t in tables
    }


async def get_schema(workspace_id: str, session: Any) -> dict[str, Any]:
    redis = await get_redis()
    key = f"lql:schema:{workspace_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    schema = await _build_schema(workspace_id, session)
    await redis.setex(key, _SCHEMA_TTL, json.dumps(schema))
    return schema


async def invalidate_schema_cache(workspace_id: str) -> None:
    redis = await get_redis()
    await redis.delete(f"lql:schema:{workspace_id}")


_TABLE_SUBQ = __import__("re").compile(
    r"table_id\s*=\s*\(SELECT\s+table_id\s+FROM\s+tables\s+"
    r"WHERE\s+table_name\s*=\s*'([^']+)'\s+AND\s+workspace_id\s*=\s*'([^']+)'\)",
    __import__("re").IGNORECASE,
)


def _fix_table_name(sql: str) -> str:
    """LatticeQL generates table_name but LatticeCast uses table_id as the name.
    Rewrite the subquery to a direct filter."""
    return _TABLE_SUBQ.sub(r"table_id = '\1' AND workspace_id = '\2'", sql)


async def compile_lql(lql: str, workspace_id: str, session: Any) -> tuple[str, list]:
    schema = await get_schema(workspace_id, session)
    try:
        sql, params = _compile(lql, schema, workspace=workspace_id)
        return _fix_table_name(sql), params
    except LatticeQLError as e:
        raise ValueError(f"{e.kind}: {e.message}") from e
