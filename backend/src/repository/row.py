# src/repository/row.py
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.row import Row, RowUpdate


class RowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, table_id: UUID, data: dict[str, Any] | None = None) -> Row:
        row = Row(table_id=table_id, data=data or {})
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, id: UUID) -> Row | None:
        return await self.session.get(Row, id)

    async def list_by_table(self, table_id: UUID, offset: int = 0, limit: int = 100) -> list[Row]:
        statement = (
            select(Row)
            .where(Row.table_id == table_id)
            .order_by(Row.created_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def update(self, row: Row, data: RowUpdate) -> Row:
        row.data = data.data
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, row: Row) -> None:
        await self.session.delete(row)
        await self.session.commit()

    async def filter_by_jsonb(self, table_id: UUID, contains: dict[str, Any], offset: int = 0, limit: int = 100) -> list[Row]:
        """Filter rows where data @> contains (JSONB containment query using GIN index)."""
        statement = (
            select(Row)
            .where(Row.table_id == table_id)
            .where(text("data @> cast(:contains as jsonb)").bindparams(contains=json.dumps(contains)))
            .order_by(Row.created_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.exec(statement)
        return list(result.all())
