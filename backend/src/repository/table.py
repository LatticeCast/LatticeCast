# src/repository/table.py
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table


class TableRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_id: str, name: str) -> Table:
        table = Table(workspace_id=workspace_id, name=name)
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def get_by_id(self, table_id: UUID) -> Table | None:
        result = await self.session.execute(
            select(Table).where(Table.table_id == table_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: str) -> list[Table]:
        result = await self.session.execute(
            select(Table).where(Table.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def update(self, table: Table, name: str) -> Table:
        table.name = name
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def delete(self, table: Table) -> None:
        await self.session.delete(table)
        await self.session.commit()

    async def add_column(self, table: Table, column_dict: dict[str, Any]) -> Table:
        table.columns = [*table.columns, column_dict]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def update_column(self, table: Table, column_id: str, updates: dict[str, Any]) -> Table:
        table.columns = [
            {**col, **updates} if col.get("column_id") == column_id else col
            for col in table.columns
        ]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def delete_column(self, table: Table, column_id: str) -> Table:
        table.columns = [col for col in table.columns if col.get("column_id") != column_id]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table
