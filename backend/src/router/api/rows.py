# router/api/rows.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.row import Row, RowCreate, RowResponse, RowUpdate
from models.table import Table
from models.user import User
from repository.row import RowRepository

router = APIRouter(tags=["rows"])


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
    """Create a new row in a table (must be owned by current user)"""
    table_result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    repo = RowRepository(session)
    return await repo.create(table_id=table_id, data=data.data)


@router.get("/tables/{table_id}/rows", response_model=list[RowResponse])
async def list_rows(
    table_id: UUID,
    offset: int = 0,
    limit: int = 100,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all rows in a table (must be owned by current user)"""
    table_result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

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
    """Update a row's data (table must be owned by current user)"""
    row = await session.get(Row, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    table_result = await session.execute(select(Table).where(Table.id == row.table_id, Table.user_id == user.id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    repo = RowRepository(session)
    return await repo.update(row=row, data=data)


@router.delete("/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    row_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a row (table must be owned by current user)"""
    row = await session.get(Row, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    table_result = await session.execute(select(Table).where(Table.id == row.table_id, Table.user_id == user.id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    repo = RowRepository(session)
    await repo.delete(row=row)
