# router/api/columns.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.column import Column, ColumnResponse, ColumnUpdate
from models.table import Table
from models.user import User

router = APIRouter(prefix="/columns", tags=["columns"])


@router.put("/{column_id}", response_model=ColumnResponse)
async def update_column(
    column_id: UUID,
    data: ColumnUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a column (table must be owned by current user)"""
    result = await session.execute(
        select(Column)
        .join(Table, Column.table_id == Table.id)
        .where(Column.id == column_id, Table.user_id == user.user_id)
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")

    if data.name is not None:
        column.name = data.name
    if data.type is not None:
        column.type = data.type
    if data.options is not None:
        column.options = data.options
    if data.position is not None:
        column.position = data.position
    session.add(column)
    await session.commit()
    await session.refresh(column)
    return column


@router.delete("/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    column_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a column (table must be owned by current user)"""
    result = await session.execute(
        select(Column)
        .join(Table, Column.table_id == Table.id)
        .where(Column.id == column_id, Table.user_id == user.user_id)
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")

    await session.delete(column)
    await session.commit()
