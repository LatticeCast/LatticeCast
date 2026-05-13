"""Column CRUD — thin wrappers around the V39 PG functions.

The two-step JSONB-write + index-DDL is atomic in PG. Python here only
handles auth, 404-mapping and the schema cache.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import invalidate_schema_cache
from middleware.auth import get_current_user, get_rls_session
from models.user import User
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("/{table_id}/columns")
async def list_columns(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    table = await _get_table_for_member(table_id, user, session)
    columns = await TableViewRepository(session).get_schema(table.workspace_id, table.table_id)
    return sorted(columns, key=lambda c: c.get("position", 0))


@router.put("/{table_id}/columns/order")
async def reorder_columns(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    """Reassign `position` on each column per the supplied UUID list.
    Columns not in the list are pushed to the end in their existing order.
    """
    table = await _get_table_for_member(table_id, user, session)
    desired_order: list[str] = list(data.get("order") or [])
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)

    index = {cid: i for i, cid in enumerate(desired_order)}
    columns.sort(key=lambda c: (index.get(c.get("column_id"), len(desired_order)), c.get("position", 0)))
    for i, c in enumerate(columns):
        c["position"] = i

    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    await invalidate_schema_cache(str(table.workspace_id))
    return columns


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    col = await TableViewRepository(session).add_column(
        table.workspace_id,
        table.table_id,
        data.get("name", ""),
        data.get("type", "text"),
        data.get("options", {}),
        data.get("position"),
        user.user_id,
    )
    await invalidate_schema_cache(str(table.workspace_id))
    return col


@router.patch("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: str,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    patch = {k: v for k, v in data.items() if k not in ("column_id", "created_at")}
    try:
        col = await TableViewRepository(session).update_column(
            table.workspace_id, table.table_id, column_id, patch, user.user_id
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found") from e
        raise
    await invalidate_schema_cache(str(table.workspace_id))
    return col


@router.delete("/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: str,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    try:
        await TableViewRepository(session).delete_column(
            table.workspace_id, table.table_id, column_id, user.user_id
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found") from e
        raise
    await invalidate_schema_cache(str(table.workspace_id))
