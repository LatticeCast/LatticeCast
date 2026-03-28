# router/api/rows.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.row import Row, RowCreate, RowResponse, RowUpdate
from models.user import User
from repository.row import RowRepository
from repository.table import TableRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(tags=["rows"])


async def _get_table_for_member(table_id: UUID, user: User, session: AsyncSession):
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
# ROWS (nested under table for create/list)
# --------------------------------------------------


@router.post("/tables/{table_id}/rows", response_model=RowResponse, status_code=status.HTTP_201_CREATED)
async def create_row(
    table_id: UUID,
    data: RowCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new row in a table (user must be a workspace member)"""
    await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    return await repo.create(table_id=table_id, row_data=data.row_data, created_by=user.user_id, updated_by=user.user_id)


@router.get("/tables/{table_id}/rows", response_model=list[RowResponse])
async def list_rows(
    table_id: UUID,
    offset: int = 0,
    limit: int = 100,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all rows in a table (user must be a workspace member)"""
    await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    return await repo.list_by_table(table_id=table_id, offset=offset, limit=limit)


# --------------------------------------------------
# ROWS (flat for update/delete)
# --------------------------------------------------


@router.put("/rows/{row_id}", response_model=RowResponse)
async def update_row(
    row_id: UUID,
    data: RowUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a row's data (user must be a workspace member)"""
    row = await session.get(Row, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    await _get_table_for_member(row.table_id, user, session)

    repo = RowRepository(session)
    return await repo.update(row=row, data=data, updated_by=user.user_id)


@router.delete("/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    row_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a row (user must be a workspace member)"""
    row = await session.get(Row, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    await _get_table_for_member(row.table_id, user, session)

    repo = RowRepository(session)
    await repo.delete(row=row)
