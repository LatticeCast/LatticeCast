# src/repository/column.py
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.column import Column, ColumnUpdate


class ColumnRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, table_id: UUID, name: str, type: str, options: dict[str, Any] | None = None, position: int = 0) -> Column:
        column = Column(table_id=table_id, name=name, type=type, options=options or {}, position=position)
        self.session.add(column)
        await self.session.commit()
        await self.session.refresh(column)
        return column

    async def get_by_id(self, id: UUID) -> Column | None:
        return await self.session.get(Column, id)

    async def list_by_table(self, table_id: UUID) -> list[Column]:
        statement = select(Column).where(Column.table_id == table_id).order_by(Column.position)
        result = await self.session.exec(statement)
        return list(result.all())

    async def update(self, column: Column, data: ColumnUpdate) -> Column:
        if data.name is not None:
            column.name = data.name
        if data.type is not None:
            column.type = data.type
        if data.options is not None:
            column.options = data.options
        if data.position is not None:
            column.position = data.position
        self.session.add(column)
        await self.session.commit()
        await self.session.refresh(column)
        return column

    async def delete(self, column: Column) -> None:
        await self.session.delete(column)
        await self.session.commit()

    async def reorder(self, table_id: UUID, column_ids: list[UUID]) -> list[Column]:
        columns = {c.id: c for c in await self.list_by_table(table_id)}
        for position, col_id in enumerate(column_ids):
            if col_id in columns:
                columns[col_id].position = position
                self.session.add(columns[col_id])
        await self.session.commit()
        return await self.list_by_table(table_id)
