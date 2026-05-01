# src/repository/table_view.py
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.table_view import TableView


def _sort_linked_list(views: list[TableView]) -> list[TableView]:
    """Return views in linked-list order (head → tail)."""
    if not views:
        return []
    referenced = {v.next_view_id for v in views if v.next_view_id is not None}
    heads = [v for v in views if v.view_number not in referenced]
    if not heads:
        return sorted(views, key=lambda v: v.view_number)
    by_number = {v.view_number: v for v in views}
    ordered: list[TableView] = []
    current: TableView | None = heads[0]
    seen: set[int] = set()
    while current and current.view_number not in seen:
        ordered.append(current)
        seen.add(current.view_number)
        current = by_number.get(current.next_view_id) if current.next_view_id else None
    remaining = [v for v in views if v.view_number not in seen]
    ordered.extend(sorted(remaining, key=lambda v: v.view_number))
    return ordered


class TableViewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_ordered(self, workspace_id: UUID, table_id: str) -> list[TableView]:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
            )
        )
        return _sort_linked_list(list(result.scalars().all()))

    async def get_by_name(self, workspace_id: UUID, table_id: str, name: str) -> TableView | None:
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
        config: dict[str, Any],
        created_by: UUID | None = None,
    ) -> TableView:
        # Use raw INSERT + RETURNING so the trigger-set view_number is captured.
        result = await self.session.execute(
            text("""
                INSERT INTO table_views
                    (workspace_id, table_id, name, type, config, created_by, updated_by)
                VALUES
                    (:workspace_id, :table_id, :name, :type,
                     CAST(:config AS jsonb), :created_by, :updated_by)
                RETURNING workspace_id, table_id, view_number, is_default,
                          next_view_id, name, type, config,
                          created_by, updated_by, created_at, updated_at
            """),
            {
                "workspace_id": str(workspace_id),
                "table_id": str(table_id),
                "name": name,
                "type": view_type,
                "config": json.dumps(config),
                "created_by": str(created_by) if created_by else None,
                "updated_by": str(created_by) if created_by else None,
            },
        )
        await self.session.commit()
        r = result.mappings().one()
        return TableView(
            workspace_id=r["workspace_id"],
            table_id=r["table_id"],
            view_number=r["view_number"],
            is_default=r["is_default"],
            next_view_id=r["next_view_id"],
            name=r["name"],
            type=r["type"],
            config=r["config"],
            created_by=r["created_by"],
            updated_by=r["updated_by"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    async def update(self, view: TableView, updates: dict[str, Any]) -> TableView:
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

    async def move(
        self,
        workspace_id: UUID,
        table_id: str,
        view: TableView,
        after_name: str | None,
    ) -> list[TableView]:
        """Reorder the linked list: move view to after after_name, or to head when None."""
        views = await self.list_ordered(workspace_id, table_id)
        moving_num = view.view_number
        remaining = [v for v in views if v.view_number != moving_num]

        if after_name is None:
            new_order = [view, *remaining]
        else:
            idx = next((i for i, v in enumerate(remaining) if v.name == after_name), None)
            if idx is None:
                raise ValueError(f"View '{after_name}' not found")
            new_order = remaining[: idx + 1] + [view] + remaining[idx + 1 :]

        for i, v in enumerate(new_order):
            new_next = new_order[i + 1].view_number if i + 1 < len(new_order) else None
            if v.next_view_id != new_next:
                v.next_view_id = new_next
                self.session.add(v)

        await self.session.commit()
        return new_order
