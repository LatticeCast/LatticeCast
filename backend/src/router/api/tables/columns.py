"""Column CRUD — every mutation returns the full table_schemas.config
({columns, view_order, default_view}) so the FE replaces its local
schema cache from the response (server is source of truth).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import invalidate_schema_cache
from middleware.auth import get_current_user, get_rls_session
from models.table import ColumnCreate, ColumnUpdate
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(prefix="/tables", tags=["tables"])


# Reads: GET /tables/{tid} returns the full schema (columns, view_order,
# default_view). Per-aspect GETs (columns, view-order) were removed in v40.
# Mutations below all return the full schema config.


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: int,
    data: ColumnCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    try:
        schema = await view_repo.add_column(
            table.workspace_id, table.table_id,
            data.name, data.type,
            data.options.model_dump(), user.user_id,
        )
    except IntegrityError as exc:
        await session.rollback()
        if "duplicate normalized column name" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A column with that name already exists",
            ) from exc
        raise
    await invalidate_schema_cache(str(table.workspace_id))
    return schema


@router.patch("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: int,
    column_id: str,
    data: ColumnUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    patch = data.model_dump(exclude_unset=True)
    if "options" in patch:
        patch["options"] = data.options.model_dump() if data.options is not None else {}
    try:
        await view_repo.update_column(
            table.workspace_id, table.table_id, column_id, patch, user.user_id
        )
    except IntegrityError as exc:
        await session.rollback()
        if "duplicate normalized column name" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A column with that name already exists",
            ) from exc
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found") from e
        raise
    await invalidate_schema_cache(str(table.workspace_id))
    return await view_repo.get_tables_schema(table.workspace_id, table.table_id)


@router.delete("/{table_id}/columns/{column_id}")
async def delete_column(
    table_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    try:
        await view_repo.delete_column(
            table.workspace_id, table.table_id, column_id, user.user_id
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found") from e
        raise
    await invalidate_schema_cache(str(table.workspace_id))
    return await view_repo.get_tables_schema(table.workspace_id, table.table_id)


# ── Per-column indexes: created on demand, never by add_column ──────────────
#
# Rows of every table share one physical table, so each index costs every write
# of every table. Select / tags / checkbox / text equality is already served by
# the shared row_data GIN. A per-column btree is allowed only on integer-valued
# types (date, datetime); `number` is not indexed by product rule, not because
# PostgreSQL cannot (indexes made for it before V79 can be listed and dropped).
#
# Known gaps, do not present these indexes as a speed-up yet:
# - No query path uses them. LatticeQL compares through a different expression
#   and finds table_id by subquery, so the partial index never applies;
#   query_rows filters by containment and sorts by row columns only.
# - CREATE / DROP INDEX here is not CONCURRENTLY: it blocks writes to the
#   shared rows table, for every tenant, for as long as it runs.
_GIN_SERVED_TYPES = frozenset({"text", "string", "select", "tags", "checkbox"})
_RANGE_INDEX_TYPES = frozenset({"date", "datetime"})


def _index_state(table: Any, column: dict[str, Any], indexes: dict[str, dict]) -> dict[str, Any]:
    col_type = column["type"]
    idx = indexes.get(TableRepository._index_name(table.workspace_id, table.table_id, column["column_id"]))
    if idx is not None:
        served_by = idx["method"]
    elif col_type in _GIN_SERVED_TYPES:
        served_by = "shared_gin"
    else:
        served_by = "none"
    return {
        "column_id": column["column_id"],
        "name": column.get("name"),
        "type": col_type,
        "index": idx,
        "served_by": served_by,
        "can_create_index": col_type in _RANGE_INDEX_TYPES,
    }


@router.get("/{table_id}/indexes")
async def list_indexes(
    table_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Which columns of this table have an index, and what serves each of the others."""
    table = await _get_table_for_member(table_id, user, session)
    schema = await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id)
    indexes = await TableRepository(session).list_column_indexes(table.workspace_id, table.table_id)
    return {"columns": [_index_state(table, c, indexes) for c in schema["columns"] if "column_id" in c and "type" in c]}


async def _column_of(table: Any, column_id: str, session: AsyncSession) -> dict[str, Any]:
    schema = await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id)
    for column in schema["columns"]:
        if column.get("column_id") == column_id:
            return column
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")


@router.post("/{table_id}/columns/{column_id}/index", status_code=status.HTTP_201_CREATED)
async def create_index(
    table_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Create the column's btree index. Only date and datetime (integer epoch-ms) qualify."""
    table = await _get_table_for_member(table_id, user, session)
    column = await _column_of(table, column_id, session)
    col_type = column["type"]
    if col_type not in _RANGE_INDEX_TYPES:
        if col_type == "number":
            reason = "number columns are not indexed; only integer-valued types (date, datetime) are"
        elif col_type in _GIN_SERVED_TYPES:
            reason = "equality on this type is already served by the shared GIN index"
        else:
            reason = "this column type has no index"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Cannot index a {col_type} column: {reason}")
    repo = TableRepository(session)
    await repo.create_column_index(table.workspace_id, table.table_id, column_id, col_type)
    indexes = await repo.list_column_indexes(table.workspace_id, table.table_id)
    return _index_state(table, column, indexes)


@router.delete("/{table_id}/columns/{column_id}/index")
async def drop_index(
    table_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Drop the column's per-column index (also one created for a number column before V79)."""
    table = await _get_table_for_member(table_id, user, session)
    column = await _column_of(table, column_id, session)
    repo = TableRepository(session)
    await repo.drop_column_index(table.workspace_id, table.table_id, column_id)
    indexes = await repo.list_column_indexes(table.workspace_id, table.table_id)
    return _index_state(table, column, indexes)
