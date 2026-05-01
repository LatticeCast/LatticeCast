# src/repository/table_view.py
# V34: One row per piece of table metadata.
#   - __schema__ row holds the column array
#   - __order__ row holds the ordered name array
#   - user-named rows hold view configs
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.table_view import (
    ORDER_ROW_NAME,
    SCHEMA_ROW_NAME,
    USER_VIEW_TYPES,
    TableView,
)


class TableViewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Generic row access ────────────────────────────────────────────────

    async def list_all(self, workspace_id: UUID, table_id: str) -> list[TableView]:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
            )
        )
        return list(result.scalars().all())

    async def get_by_name(
        self, workspace_id: UUID, table_id: str, name: str
    ) -> TableView | None:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        workspace_id: UUID,
        table_id: str,
        name: str,
        view_type: str,
        config: dict[str, Any] | list[Any],
        created_by: UUID | None = None,
    ) -> TableView:
        view = TableView(
            workspace_id=workspace_id,
            table_id=table_id,
            name=name,
            type=view_type,
            config=config,
            created_by=created_by,
            updated_by=created_by,
        )
        self.session.add(view)
        await self.session.commit()
        await self.session.refresh(view)
        return view

    async def update(
        self, view: TableView, updates: dict[str, Any]
    ) -> TableView:
        for k, v in updates.items():
            setattr(view, k, v)
        view.updated_at = datetime.utcnow()
        self.session.add(view)
        await self.session.commit()
        await self.session.refresh(view)
        return view

    async def delete(self, view: TableView) -> None:
        await self.session.delete(view)
        await self.session.commit()

    # ── User views (excludes schema + order rows) ────────────────────────

    async def list_user_views(
        self, workspace_id: UUID, table_id: str
    ) -> list[TableView]:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.type.in_(USER_VIEW_TYPES),  # type: ignore[attr-defined]
            )
        )
        return list(result.scalars().all())

    # ── __schema__ row helpers ───────────────────────────────────────────

    async def get_schema(
        self, workspace_id: UUID, table_id: str
    ) -> list[dict[str, Any]]:
        view = await self.get_by_name(workspace_id, table_id, SCHEMA_ROW_NAME)
        if view is None or not isinstance(view.config, list):
            return []
        return view.config

    async def set_schema(
        self,
        workspace_id: UUID,
        table_id: str,
        columns: list[dict[str, Any]],
        updated_by: UUID | None = None,
    ) -> list[dict[str, Any]]:
        view = await self.get_by_name(workspace_id, table_id, SCHEMA_ROW_NAME)
        if view is None:
            view = await self.create(
                workspace_id=workspace_id,
                table_id=table_id,
                name=SCHEMA_ROW_NAME,
                view_type="schema",
                config=columns,
                created_by=updated_by,
            )
            return columns
        await self.update(view, {"config": columns, "updated_by": updated_by})
        return columns

    # ── __order__ row helpers ────────────────────────────────────────────

    async def get_order(
        self, workspace_id: UUID, table_id: str
    ) -> list[str]:
        view = await self.get_by_name(workspace_id, table_id, ORDER_ROW_NAME)
        if view is None or not isinstance(view.config, list):
            return []
        return view.config

    async def set_order(
        self,
        workspace_id: UUID,
        table_id: str,
        order: list[str],
        updated_by: UUID | None = None,
    ) -> list[str]:
        view = await self.get_by_name(workspace_id, table_id, ORDER_ROW_NAME)
        if view is None:
            await self.create(
                workspace_id=workspace_id,
                table_id=table_id,
                name=ORDER_ROW_NAME,
                view_type="order",
                config=order,
                created_by=updated_by,
            )
            return order
        await self.update(view, {"config": order, "updated_by": updated_by})
        return order
