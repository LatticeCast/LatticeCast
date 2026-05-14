"""Column CRUD — every mutation returns the full table_schemas.config
({columns, view_order, default_view}) so the FE replaces its local
schema cache from the response (server is source of truth).
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
    """Read-only — array index IS the column position."""
    table = await _get_table_for_member(table_id, user, session)
    return await TableViewRepository(session).get_schema(table.workspace_id, table.table_id)


# col_order is now a sub-field of PATCH /tables/{tid}/schema in crud.py.


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    await view_repo.add_column(
        table.workspace_id, table.table_id,
        data.get("name", ""), data.get("type", "text"),
        data.get("options", {}), user.user_id,
    )
    await invalidate_schema_cache(str(table.workspace_id))
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)


@router.patch("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: str,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    patch = {k: v for k, v in data.items() if k not in ("column_id", "created_at", "position")}
    try:
        await view_repo.update_column(
            table.workspace_id, table.table_id, column_id, patch, user.user_id
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found") from e
        raise
    await invalidate_schema_cache(str(table.workspace_id))
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)


@router.delete("/{table_id}/columns/{column_id}")
async def delete_column(
    table_id: str,
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
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)
