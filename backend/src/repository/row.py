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
        workspace_id: UUID,
        table_id: str,
        row_data: dict[str, Any] | None = None,
        created_by: UUID | None = None,
        updated_by: UUID | None = None,
    ) -> Row:
        # Use raw INSERT + RETURNING because PG trigger sets row_id
        # and SQLAlchemy can't track the PK change from 0 → actual value
        from sqlalchemy import text

        result = await self.session.execute(
            text("""
                INSERT INTO rows (workspace_id, table_id, row_data, created_by, updated_by)
                VALUES (:workspace_id, :table_id, CAST(:row_data AS jsonb), :created_by, :updated_by)
                RETURNING workspace_id, table_id, row_id, row_data, created_by, updated_by, created_at, updated_at
            """),
            {
                "workspace_id": str(workspace_id),
                "table_id": str(table_id),
                "row_data": json.dumps(row_data or {}),
                "created_by": str(created_by) if created_by else None,
                "updated_by": str(updated_by) if updated_by else None,
            },
        )
        await self.session.commit()
        r = result.mappings().one()
        return Row(
            workspace_id=r["workspace_id"],
            table_id=r["table_id"],
            row_id=r["row_id"],
            row_data=r["row_data"],
            created_by=r["created_by"],
            updated_by=r["updated_by"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    async def get_by_number(self, workspace_id: UUID, table_id: str, row_id: int) -> Row | None:
        result = await self.session.execute(
            select(Row).where(Row.workspace_id == workspace_id, Row.table_id == table_id, Row.row_id == row_id)
        )
        return result.scalar_one_or_none()

    async def list_by_table(
        self, workspace_id: UUID, table_id: str, offset: int = 0, limit: int = 100, sort: str = "desc"
    ) -> list[Row]:
        order = Row.row_id.desc() if sort == "desc" else Row.row_id.asc()
        statement = (
            select(Row)
            .where(Row.workspace_id == workspace_id, Row.table_id == table_id)
            .order_by(order)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update(self, row: Row, data: RowUpdate, updated_by: UUID | None = None) -> Row:
        next_row_data = {**(row.row_data or {}), **data.row_data}
        next_updated_at = datetime.utcnow()
        result = await self.session.execute(
            text("""
                UPDATE rows
                SET row_data = CAST(:row_data AS jsonb),
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE workspace_id = :workspace_id
                  AND table_id = :table_id
                  AND row_id = :row_id
                RETURNING workspace_id, table_id, row_id, row_data, created_by, updated_by, created_at, updated_at
            """),
            {
                "workspace_id": str(row.workspace_id),
                "table_id": str(row.table_id),
                "row_id": row.row_id,
                "row_data": json.dumps(next_row_data),
                "updated_by": str(updated_by) if updated_by else None,
                "updated_at": next_updated_at,
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Row disappeared during update")
        return Row(
            workspace_id=updated["workspace_id"],
            table_id=updated["table_id"],
            row_id=updated["row_id"],
            row_data=updated["row_data"],
            created_by=updated["created_by"],
            updated_by=updated["updated_by"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )

    async def remove_cell(self, row: Row, column_id: str, updated_by: UUID | None = None) -> Row:
        """Remove a system-managed cell value while preserving other row data."""
        next_row_data = {key: value for key, value in (row.row_data or {}).items() if key != column_id}
        next_updated_at = datetime.utcnow()
        result = await self.session.execute(
            text("""
                UPDATE rows
                SET row_data = CAST(:row_data AS jsonb),
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE workspace_id = :workspace_id
                  AND table_id = :table_id
                  AND row_id = :row_id
                RETURNING workspace_id, table_id, row_id, row_data, created_by, updated_by, created_at, updated_at
            """),
            {
                "workspace_id": str(row.workspace_id),
                "table_id": str(row.table_id),
                "row_id": row.row_id,
                "row_data": json.dumps(next_row_data),
                "updated_by": str(updated_by) if updated_by else None,
                "updated_at": next_updated_at,
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Row disappeared during cell removal")
        return Row(
            workspace_id=updated["workspace_id"],
            table_id=updated["table_id"],
            row_id=updated["row_id"],
            row_data=updated["row_data"],
            created_by=updated["created_by"],
            updated_by=updated["updated_by"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )

    async def delete(self, row: Row) -> None:
        await self.session.delete(row)
        await self.session.commit()

    async def count_by_table(self, workspace_id: UUID, table_id: str) -> int:
        """Return total number of rows in a table."""
        from sqlalchemy import func

        statement = select(func.count()).where(Row.workspace_id == workspace_id, Row.table_id == table_id)
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def filter_by_jsonb(
        self, workspace_id: UUID, table_id: str, contains: dict[str, Any], offset: int = 0, limit: int = 100
    ) -> list[Row]:
        """Filter rows where row_data @> contains (JSONB containment query using GIN index)."""
        statement = (
            select(Row)
            .where(Row.workspace_id == workspace_id, Row.table_id == table_id)
            .where(text("row_data @> cast(:contains as jsonb)").bindparams(contains=json.dumps(contains)))
            .order_by(Row.row_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
