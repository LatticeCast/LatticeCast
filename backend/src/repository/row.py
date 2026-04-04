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

    async def create(
        self,
        table_id: UUID,
        row_data: dict[str, Any] | None = None,
        created_by: UUID | None = None,
        updated_by: UUID | None = None,
    ) -> Row:
        row = Row(table_id=table_id, row_data=row_data or {}, created_by=created_by, updated_by=updated_by)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, row_id: UUID) -> Row | None:
        return await self.session.get(Row, row_id)

    async def get_by_number(self, table_id: UUID, row_number: int) -> Row | None:
        result = await self.session.execute(select(Row).where(Row.table_id == table_id, Row.row_number == row_number))
        return result.scalar_one_or_none()

    async def list_by_table(self, table_id: UUID, offset: int = 0, limit: int = 100) -> list[Row]:
        statement = select(Row).where(Row.table_id == table_id).order_by(Row.row_number).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update(self, row: Row, data: RowUpdate, updated_by: UUID | None = None) -> Row:
        row.row_data = data.row_data
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, row: Row) -> None:
        await self.session.delete(row)
        await self.session.commit()

    async def count_by_table(self, table_id: UUID) -> int:
        """Return total number of rows in a table."""
        from sqlalchemy import func

        statement = select(func.count()).where(Row.table_id == table_id)
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def filter_by_jsonb(
        self, table_id: UUID, contains: dict[str, Any], offset: int = 0, limit: int = 100
    ) -> list[Row]:
        """Filter rows where row_data @> contains (JSONB containment query using GIN index)."""
        statement = (
            select(Row)
            .where(Row.table_id == table_id)
            .where(text("row_data @> cast(:contains as jsonb)").bindparams(contains=json.dumps(contains)))
            .order_by(Row.row_number)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
