# src/repository/table.py
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table

# Column types that get B-tree expression indexes (sortable/range queries)
BTREE_TYPES = {"number", "date"}
# Column types that get GIN indexes (containment/grouping queries)
GIN_TYPES = {"select", "tags", "text", "string", "url", "checkbox"}


class TableRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_id: UUID, name: str) -> Table:
        table = Table(workspace_id=workspace_id, name=name)
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def get_by_id(self, table_id: UUID) -> Table | None:
        result = await self.session.execute(select(Table).where(Table.table_id == table_id))
        return result.scalar_one_or_none()

    async def resolve_table(self, workspace_id: UUID, identifier: str) -> Table | None:
        """Resolve a table within a workspace by UUID first, then case-insensitive name."""
        try:
            table_uuid = UUID(identifier)
            result = await self.session.execute(
                select(Table).where(
                    Table.table_id == table_uuid,
                    Table.workspace_id == workspace_id,
                )
            )
            table = result.scalar_one_or_none()
            if table:
                return table
        except (ValueError, AttributeError):
            pass
        # Fallback: case-insensitive name match within workspace
        result = await self.session.execute(
            select(Table).where(
                Table.workspace_id == workspace_id,
                func.lower(Table.name) == identifier.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def resolve_table_global(self, identifier: str, workspace_ids: list[UUID]) -> Table | None:
        """Resolve a table by UUID (global) or case-insensitive name across the given workspaces."""
        try:
            table_uuid = UUID(identifier)
            return await self.get_by_id(table_uuid)
        except (ValueError, AttributeError):
            pass
        if not workspace_ids:
            return None
        result = await self.session.execute(
            select(Table).where(
                Table.workspace_id.in_(workspace_ids),
                func.lower(Table.name) == identifier.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: UUID) -> list[Table]:
        result = await self.session.execute(select(Table).where(Table.workspace_id == workspace_id))
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
        table.columns = [{**col, **updates} if col.get("column_id") == column_id else col for col in table.columns]
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

    async def add_view(self, table: Table, view_dict: dict[str, Any]) -> Table:
        table.views = [*table.views, view_dict]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def update_view(self, table: Table, view_name: str, updates: dict[str, Any]) -> Table:
        table.views = [{**v, **updates} if v.get("name") == view_name else v for v in table.views]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def delete_view(self, table: Table, view_name: str) -> Table:
        table.views = [v for v in table.views if v.get("name") != view_name]
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    # ── Index management ─────────────────────────────────────────────────

    def _index_name(self, table_id: UUID, column_id: str) -> str:
        """Generate a deterministic index name from table_id + column_id."""
        tid = str(table_id).replace("-", "")[:12]
        cid = column_id.replace("-", "")[:12]
        return f"idx_rd_{tid}_{cid}"

    async def create_column_index(self, table_id: UUID, column_id: str, col_type: str) -> None:
        """Create a PG index on row_data->column_id based on column type."""
        idx_name = self._index_name(table_id, column_id)
        table_id_str = str(table_id)

        if col_type in BTREE_TYPES:
            if col_type == "number":
                expr = f"((row_data->>'{column_id}')::numeric)"
            else:  # date → B-tree on text (ISO dates sort correctly as text)
                expr = f"((row_data->>'{column_id}'))"
            sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON rows ({expr}) WHERE table_id = '{table_id_str}'"
        elif col_type in GIN_TYPES:
            sql = (
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON rows USING GIN ((row_data->'{column_id}')) "
                f"WHERE table_id = '{table_id_str}'"
            )
        else:
            return

        await self.session.execute(text(sql))
        await self.session.commit()

    async def drop_column_index(self, table_id: UUID, column_id: str) -> None:
        """Drop the PG index for a column if it exists."""
        idx_name = self._index_name(table_id, column_id)
        await self.session.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
        await self.session.commit()
