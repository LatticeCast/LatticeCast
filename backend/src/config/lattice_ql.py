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
#
# `datetime` passes through as itself from lattice-ql 0.3.0, which added it to
# ColumnKind, let bucket() accept it, and taught codegen to read the cell as
# epoch milliseconds instead of casting it to timestamptz. Against 0.2.0 it
# had to be reported as `date`.
_LQL_KIND_BY_COLUMN_TYPE: dict[str, str] = {
    "text": "text",
    "string": "text",
    "number": "number",
    "date": "date",
    "datetime": "datetime",
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


def _inline_workspace(sql: str, workspace_id: str) -> str:
    return sql.replace("$1", f"'{workspace_id}'")


# LatticeQL's contract: $1 is always workspace_id, and any further $N are the
# query's own parameters in order of first appearance. We inline $1 and have
# no way to bind the rest -- compile() returns only a string, and the names
# behind $2.. live in Codegen._param_names, which is private.
_REMAINING_PARAM = re.compile(r"\$([2-9]\d*)")


async def compile_lql(lql: str, workspace_id: str, session: Any) -> tuple[str, list]:
    schema = await get_schema(workspace_id, session)
    try:
        sql = _compile(lql, schema)
    except LatticeQLError as e:
        raise ValueError(str(e)) from e
    sql = _inline_workspace(sql, workspace_id)

    # Fail here rather than hand PostgreSQL a query it cannot execute. An
    # unbound placeholder used to reach the database and come back as
    # 'there is no parameter $2' -- a 500 that reads like a server fault for
    # what is really an unsupported query. Supporting parameters needs
    # LatticeQL to expose the names behind them; reproducing its numbering on
    # this side would couple us to its internals.
    leftover = sorted({int(n) for n in _REMAINING_PARAM.findall(sql)})
    if leftover:
        placeholders = ", ".join(f"${n}" for n in leftover)
        raise ValueError(
            f"query parameters are not supported yet: {placeholders} left unbound"
        )

    return sql, []
