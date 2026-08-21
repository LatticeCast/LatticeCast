# src/repository/row.py
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.row import Row, RowPut, RowUpdate


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
        """Backward-compatible alias for a partial row-data mutation."""
        return await self.patch_row(row, data, updated_by)

    async def update_row(self, row: Row, data: RowUpdate, updated_by: UUID | None = None) -> Row:
        """Backward-compatible alias for ``patch_row``."""
        return await self.patch_row(row, data, updated_by)

    async def patch_row(self, row: Row, data: RowUpdate, updated_by: UUID | None = None) -> Row:
        """Pass a partial non-blob patch directly to PostgreSQL."""
        result = await self.session.execute(
            text("""
                SELECT *
                FROM public.patch_row_data(
                    :workspace_id,
                    :table_id,
                    :row_id,
                    CAST(:patch AS jsonb)
                )
            """),
            {
                "workspace_id": str(row.workspace_id),
                "table_id": str(row.table_id),
                "row_id": row.row_id,
                "patch": json.dumps(data.row_data),
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Row disappeared during update")
        return self._row_from_mapping(updated)

    async def put_row(self, row: Row, data: RowPut, updated_by: UUID | None = None) -> Row:
        """Pass complete non-blob row data directly to PostgreSQL."""
        result = await self.session.execute(
            text("""
                SELECT *
                FROM public.put_row_data(
                    :workspace_id,
                    :table_id,
                    :row_id,
                    CAST(:data AS jsonb)
                )
            """),
            {
                "workspace_id": str(row.workspace_id),
                "table_id": str(row.table_id),
                "row_id": row.row_id,
                "data": json.dumps(data.row_data),
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Row disappeared during update")
        return self._row_from_mapping(updated)

    async def update_blob(
        self, row: Row, column_id: str, metadata: dict[str, Any], updated_by: UUID | None = None
    ) -> Row:
        """Write metadata for exactly one blob cell through PostgreSQL."""
        result = await self.session.execute(
            text("""
                SELECT *
                FROM public.update_blob_cell(
                    :workspace_id,
                    :table_id,
                    :row_id,
                    :column_id,
                    CAST(:metadata AS jsonb)
                )
            """),
            {
                "workspace_id": str(row.workspace_id),
                "table_id": str(row.table_id),
                "row_id": row.row_id,
                "column_id": column_id,
                "metadata": json.dumps(metadata),
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Row disappeared during blob update")
        return self._row_from_mapping(updated)

    async def remove_cell(self, row: Row, column_id: str, updated_by: UUID | None = None) -> Row:
        """Clear system-managed blob metadata through its dedicated PG function."""
        return await self.update_blob(row, column_id, {}, updated_by)

    @staticmethod
    def _row_from_mapping(updated: Any) -> Row:
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
