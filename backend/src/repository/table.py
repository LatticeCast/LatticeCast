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

    async def create(
        self,
        workspace_id: UUID,
        table_id: str,
        columns: list[dict[str, Any]] | None = None,
        views: list[dict[str, Any]] | None = None,
    ) -> Table:
        """Atomic create — columns and views set in initial insert."""
        table = Table(
            workspace_id=workspace_id,
            table_id=table_id.lower(),
            columns=columns or [],
            views=views or [],
        )
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def get_by_id(self, workspace_id: UUID, table_id: str) -> Table | None:
        result = await self.session.execute(
            select(Table).where(Table.workspace_id == workspace_id, Table.table_id == table_id)
        )
        return result.scalar_one_or_none()

    async def resolve_table(self, workspace_id: UUID, identifier: str) -> Table | None:
        """Resolve a table by table_id (case-insensitive) within a workspace."""
        result = await self.session.execute(
            select(Table).where(
                Table.workspace_id == workspace_id,
                func.lower(Table.table_id) == identifier.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def resolve_table_global(self, identifier: str, workspace_ids: list[UUID]) -> Table | None:
        """Resolve a table by case-insensitive name across the given workspaces.
        If the same table_id exists in multiple workspaces, returns the first match."""
        if not workspace_ids:
            return None
        result = await self.session.execute(
            select(Table).where(
                Table.workspace_id.in_(workspace_ids),
                func.lower(Table.table_id) == identifier.lower(),
            )
        )
        return result.scalars().first()

    async def list_by_workspace(self, workspace_id: UUID) -> list[Table]:
        result = await self.session.execute(select(Table).where(Table.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def update(self, table: Table, table_id: str) -> Table:
        table.table_id = table_id.lower()
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

    async def delete(self, table: Table) -> None:
        await self.session.delete(table)
        await self.session.commit()

    async def set_columns(self, table: Table, columns: list[dict[str, Any]]) -> Table:
        table.columns = columns
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        await self.session.commit()
        await self.session.refresh(table)
        return table

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

    def _index_name(self, table_id: str, column_id: str) -> str:
        """Generate a deterministic index name from table_id + column_id."""
        tid = table_id.replace("-", "")[:12]
        cid = column_id.replace("-", "")[:12]
        return f"idx_rd_{tid}_{cid}"

    async def create_column_index(self, table_id: str, column_id: str, col_type: str) -> None:
        """Create a PG index on row_data->column_id via SECURITY DEFINER function.

        app_user has no DDL; the migration (V27) defines create_row_data_index
        as SECURITY DEFINER owned by dba, so we call it via SELECT.
        """
        idx_name = self._index_name(table_id, column_id)
        if col_type not in BTREE_TYPES and col_type not in GIN_TYPES:
            return
        await self.session.execute(
            text(
                "SELECT create_row_data_index(:idx, :tid, :cid, :ct)"
            ).bindparams(idx=idx_name, tid=str(table_id), cid=column_id, ct=col_type)
        )
        await self.session.commit()

    async def drop_column_index(self, table_id: str, column_id: str) -> None:
        """Drop the PG index via SECURITY DEFINER function."""
        idx_name = self._index_name(table_id, column_id)
        await self.session.execute(
            text("SELECT drop_row_data_index(:idx)").bindparams(idx=idx_name)
        )
        await self.session.commit()
