# router/api/tables.py

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.table import Table, TableCreate, TableResponse, TableUpdate
from models.user import User
from repository.table import TableRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(prefix="/tables", tags=["tables"])


async def _get_table_for_member(
    table_id: UUID,
    user: User,
    session: AsyncSession,
) -> Table:
    """Fetch table and verify the current user is a member of its workspace."""
    table_repo = TableRepository(session)
    table = await table_repo.get_by_id(table_id)
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    ws_repo = WorkspaceRepository(session)
    if not await ws_repo.is_member(table.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


# --------------------------------------------------
# TABLES
# --------------------------------------------------


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new table in the user's default workspace"""
    ws_repo = WorkspaceRepository(session)
    if not await ws_repo.is_member(user.user_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No default workspace found")
    table_repo = TableRepository(session)
    return await table_repo.create(workspace_id=user.user_id, name=data.name)


@router.get("", response_model=list[TableResponse])
async def list_tables(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all tables across workspaces the current user is a member of"""
    ws_repo = WorkspaceRepository(session)
    workspaces = await ws_repo.list_by_user(user.user_id)
    table_repo = TableRepository(session)
    tables: list[Table] = []
    for ws in workspaces:
        tables.extend(await table_repo.list_by_workspace(ws.workspace_id))
    return tables


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a table by ID (user must be a workspace member)"""
    return await _get_table_for_member(table_id, user, session)


@router.put("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: UUID,
    data: TableUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a table name (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    return await table_repo.update(table, data.name)


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a table (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    await table_repo.delete(table)


# --------------------------------------------------
# COLUMNS (stored in tables.columns JSONB)
# --------------------------------------------------


@router.get("/{table_id}/columns")
async def list_columns(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List columns for a table (sorted by position)"""
    table = await _get_table_for_member(table_id, user, session)
    return sorted(table.columns, key=lambda c: c.get("position", 0))


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: UUID,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a column to a table"""
    table = await _get_table_for_member(table_id, user, session)
    column_dict: dict[str, Any] = {
        "column_id": str(uuid4()),
        "name": data.get("name", ""),
        "type": data.get("type", "text"),
        "options": data.get("options", {}),
        "position": data.get("position", len(table.columns)),
        "created_at": datetime.utcnow().isoformat(),
    }
    table_repo = TableRepository(session)
    updated = await table_repo.add_column(table, column_dict)
    await table_repo.create_column_index(table_id, column_dict["column_id"], column_dict["type"])
    return updated.columns[-1]


@router.put("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: UUID,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a column in the table's columns JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(c.get("column_id") == column_id for c in table.columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    # strip immutable fields from updates
    updates = {k: v for k, v in data.items() if k not in ("column_id", "created_at")}
    table_repo = TableRepository(session)
    # If type changed, recreate index
    if "type" in updates:
        old_col = next(c for c in table.columns if c.get("column_id") == column_id)
        if updates["type"] != old_col.get("type"):
            await table_repo.drop_column_index(table_id, column_id)
            await table_repo.create_column_index(table_id, column_id, updates["type"])
    updated = await table_repo.update_column(table, column_id, updates)
    col = next(c for c in updated.columns if c.get("column_id") == column_id)
    return col


@router.delete("/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: UUID,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a column from the table's columns JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(c.get("column_id") == column_id for c in table.columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    table_repo = TableRepository(session)
    await table_repo.drop_column_index(table_id, column_id)
    await table_repo.delete_column(table, column_id)


# --------------------------------------------------
# VIEWS (stored in tables.views JSONB)
# --------------------------------------------------


@router.get("/{table_id}/views")
async def list_views(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List views for a table"""
    table = await _get_table_for_member(table_id, user, session)
    return table.views


@router.post("/{table_id}/views", status_code=status.HTTP_201_CREATED)
async def create_view(
    table_id: UUID,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a view to a table"""
    table = await _get_table_for_member(table_id, user, session)
    name = data.get("name", "")
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="View name is required")
    if any(v.get("name") == name for v in table.views):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
    view_dict: dict[str, Any] = {
        "name": name,
        "type": data.get("type", "table"),
        "config": data.get("config", {}),
    }
    table_repo = TableRepository(session)
    updated = await table_repo.add_view(table, view_dict)
    return updated.views[-1]


@router.put("/{table_id}/views/{view_name}")
async def update_view(
    table_id: UUID,
    view_name: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a view's config in the table's views JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(v.get("name") == view_name for v in table.views):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    updates = {k: v for k, v in data.items() if k != "name"}
    table_repo = TableRepository(session)
    updated = await table_repo.update_view(table, view_name, updates)
    return next(v for v in updated.views if v.get("name") == view_name)


@router.delete("/{table_id}/views/{view_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    table_id: UUID,
    view_name: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove a view from the table's views JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(v.get("name") == view_name for v in table.views):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    table_repo = TableRepository(session)
    await table_repo.delete_view(table, view_name)
