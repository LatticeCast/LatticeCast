# router/api/tables.py

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.column import Column, ColumnCreate, ColumnResponse
from models.table import Table, TableCreate, TableResponse, TableUpdate
from models.user import User

router = APIRouter(prefix="/tables", tags=["tables"])


# --------------------------------------------------
# TABLES
# --------------------------------------------------


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new table for the current user"""
    table = Table(user_id=user.user_id, name=data.name)
    session.add(table)
    await session.commit()
    await session.refresh(table)
    return table


@router.get("", response_model=list[TableResponse])
async def list_tables(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all tables owned by the current user"""
    result = await session.execute(select(Table).where(Table.user_id == user.user_id))
    return list(result.scalars().all())


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a table by ID (must be owned by current user)"""
    result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.user_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.put("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: UUID,
    data: TableUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a table name (must be owned by current user)"""
    result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.user_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    table.name = data.name
    table.updated_at = datetime.utcnow()
    session.add(table)
    await session.commit()
    await session.refresh(table)
    return table


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a table (must be owned by current user)"""
    result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.user_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    await session.delete(table)
    await session.commit()


# --------------------------------------------------
# COLUMNS (nested under table)
# --------------------------------------------------


@router.get("/{table_id}/columns", response_model=list[ColumnResponse])
async def list_columns(
    table_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all columns for a table (must be owned by current user)"""
    table_result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.user_id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    result = await session.execute(select(Column).where(Column.table_id == table_id).order_by(Column.position))
    return list(result.scalars().all())


@router.post("/{table_id}/columns", response_model=ColumnResponse, status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: UUID,
    data: ColumnCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new column in a table (must be owned by current user)"""
    table_result = await session.execute(select(Table).where(Table.id == table_id, Table.user_id == user.user_id))
    if not table_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    column = Column(table_id=table_id, name=data.name, type=data.type, options=data.options, position=data.position)
    session.add(column)
    await session.commit()
    await session.refresh(column)
    return column
