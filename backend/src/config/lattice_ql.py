from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from lattice_ql import compile as _compile
from lattice_ql.error import LatticeQLError

from config.pg_cache import cache_delete, cache_get, cache_set
from repository.table import TableRepository
from repository.table_view import TableViewRepository

_SCHEMA_TTL = 60  # seconds

# LatticeCast's column types and LatticeQL's ColumnKind are two different
# vocabularies, and passing ours through unmapped fails schema validation for
# the WHOLE workspace, not just the offending column - so one blob column
# breaks every dashboard query in that workspace. Four of our ten types have
# no counterpart under their own name:
#
#   string   -> LatticeQL has only `text`
#   checkbox -> it calls this `bool`
#   blob     -> it calls this `doc`
#   datetime -> it has no datetime; `date` is correct here because both types
#               share one storage shape (epoch milliseconds, V48/V49) and
#               LatticeQL only uses the kind to gate bucket()
_LQL_KIND_BY_COLUMN_TYPE: dict[str, str] = {
    "text": "text",
    "string": "text",
    "number": "number",
    "date": "date",
    "datetime": "date",
    "select": "select",
    "tags": "tags",
    "checkbox": "bool",
    "url": "url",
    "blob": "doc",
}


async def _build_schema(workspace_id: str, session: Any) -> dict[str, Any]:
    """Build the LatticeQL workspace schema from each table's __schema__ row."""
    table_repo = TableRepository(session)
    view_repo = TableViewRepository(session)
    tables = await table_repo.list_by_workspace(UUID(workspace_id))
    out: dict[str, Any] = {}
    for t in tables:
        cols = (await view_repo.get_tables_schema(t.workspace_id, t.table_id))["columns"]
        columns: dict[str, Any] = {}
        for c in cols:
            if not ("name" in c and "column_id" in c and "type" in c):
                continue
            kind = _LQL_KIND_BY_COLUMN_TYPE.get(c["type"])
            if kind is None:
                # Omit rather than pass an unknown kind through. A missing
                # column fails only the queries that name it; an unknown kind
                # fails schema validation and takes the workspace with it.
                continue
            columns[c["name"].lower().replace(" ", "_")] = {
                "id": c["column_id"],
                "type": kind,
            }
        out[t.table_id] = {"table_id": t.table_id, "columns": columns}
    return out


async def get_schema(workspace_id: str, session: Any) -> dict[str, Any]:
    key = f"lql:schema:{workspace_id}"
    try:
        cached = await cache_get(key)
        if cached:
            return cached
    except Exception:
        pass
    schema = await _build_schema(workspace_id, session)
    try:
        await cache_set(key, schema, _SCHEMA_TTL)
    except Exception:
        pass
    return schema


async def invalidate_schema_cache(workspace_id: str) -> None:
    try:
        await cache_delete(f"lql:schema:{workspace_id}")
    except Exception:
        pass


_TABLE_SUBQ = re.compile(
    r"table_id\s*=\s*\(SELECT\s+table_id\s+FROM\s+tables\s+"
    r"WHERE\s+table_name\s*=\s*'([^']+)'\s+AND\s+workspace_id\s*=\s*'([^']+)'\)",
    re.IGNORECASE,
)


def _fix_table_name(sql: str) -> str:
    """LatticeQL generates table_name but LatticeCast uses table_id as the name.
    Rewrite the subquery to a direct filter."""
    return _TABLE_SUBQ.sub(r"table_id = '\1' AND workspace_id = '\2'", sql)


def _inline_workspace(sql: str, workspace_id: str) -> str:
    return sql.replace("$1", f"'{workspace_id}'")


async def compile_lql(lql: str, workspace_id: str, session: Any) -> tuple[str, list]:
    schema = await get_schema(workspace_id, session)
    try:
        sql = _compile(lql, schema)
    except LatticeQLError as e:
        raise ValueError(str(e)) from e
    return _fix_table_name(_inline_workspace(sql, workspace_id)), []
