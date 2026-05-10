from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import invalidate_schema_cache
from middleware.auth import get_current_user, get_rls_session
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(tags=["tables"])


@router.get("/{table_id}/columns")
async def list_columns(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    return sorted(columns, key=lambda c: c.get("position", 0))


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    column_dict: dict[str, Any] = {
        "column_id": str(uuid4()),
        "name": data.get("name", ""),
        "type": data.get("type", "text"),
        "options": data.get("options", {}),
        "position": data.get("position", len(columns)),
        "created_at": datetime.utcnow().isoformat(),
    }
    columns = [*columns, column_dict]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    table_repo = TableRepository(session)
    await table_repo.create_column_index(table.table_id, column_dict["column_id"], column_dict["type"])
    await invalidate_schema_cache(str(table.workspace_id))
    return column_dict


@router.put("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: str,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    if not any(c.get("column_id") == column_id for c in columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")

    updates = {k: v for k, v in data.items() if k not in ("column_id", "created_at")}
    table_repo = TableRepository(session)

    if "type" in updates:
        old_col = next(c for c in columns if c.get("column_id") == column_id)
        if updates["type"] != old_col.get("type"):
            await table_repo.drop_column_index(table.table_id, column_id)
            await table_repo.create_column_index(table.table_id, column_id, updates["type"])

    columns = [{**c, **updates} if c.get("column_id") == column_id else c for c in columns]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    await invalidate_schema_cache(str(table.workspace_id))
    return next(c for c in columns if c.get("column_id") == column_id)


@router.delete("/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: str,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    if not any(c.get("column_id") == column_id for c in columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    table_repo = TableRepository(session)
    await table_repo.drop_column_index(table.table_id, column_id)
    columns = [c for c in columns if c.get("column_id") != column_id]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    await invalidate_schema_cache(str(table.workspace_id))
