# src/repository/table_view.py
# V44+: public.table_views holds ONLY user view rows
#       (type ∈ {table, kanban, timeline, dashboard}).
# V44+: schema/order/default_view metadata moved to public.table_schemas;
#       the per-op PG functions defined in V45-V47 do all writes. This
#       repo is now mostly a thin pass-through over those functions.
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.table_view import USER_VIEW_TYPES, TableView


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

    async def get_by_name(self, workspace_id: UUID, table_id: str, name: str) -> TableView | None:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_user_views(self, workspace_id: UUID, table_id: str) -> list[TableView]:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.type.in_(USER_VIEW_TYPES),  # type: ignore[attr-defined]
            )
        )
        return list(result.scalars().all())

    # ── User-view CRUD (V47 PG functions: atomic with view_order) ─────────

    async def create_view(
        self,
        workspace_id: UUID,
        table_id: str,
        name: str,
        view_type: str,
        config: dict[str, Any] | list[Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        """V47 create_view: inserts the user-view row AND appends the name
        to table_schemas.config.view_order in one transaction. Returns
        the new full table_schemas.config blob."""
        result = await self.session.execute(
            sa_text(
                "SELECT create_view(CAST(:ws AS uuid), :tid, :name, :type, "
                "CAST(:config AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": name,
                "type": view_type,
                "config": json.dumps(config),
                "by": str(created_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    async def update_view(
        self,
        workspace_id: UUID,
        table_id: str,
        old_name: str,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        """V47 update_view: edits the row AND keeps view_order +
        default_view consistent on rename."""
        result = await self.session.execute(
            sa_text(
                "SELECT update_view(CAST(:ws AS uuid), :tid, :old_name, "
                "CAST(:patch AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "old_name": old_name,
                "patch": json.dumps(patch),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    async def delete_view(
        self,
        workspace_id: UUID,
        table_id: str,
        name: str,
        deleted_by: UUID,
    ) -> dict[str, Any]:
        """V47 delete_view: removes the row, strips from view_order,
        clears default_view if it pointed here. Returns new config."""
        result = await self.session.execute(
            sa_text(
                "SELECT delete_view(CAST(:ws AS uuid), :tid, :name, "
                "CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": name,
                "by": str(deleted_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    # ── Schema reads (V44 table_schemas) ─────────────────────────────────

    async def get_full_schema(self, workspace_id: UUID, table_id: str) -> dict[str, Any]:
        """Return the entire table_schemas.config blob —
        {columns, view_order, default_view}. Used by mutation endpoints
        to return the new full state in one shape (FE-source-of-truth)."""
        result = await self.session.execute(
            sa_text(
                "SELECT config FROM public.table_schemas "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        if not row or row[0] is None:
            return {"columns": [], "view_order": [], "default_view": None}
        cfg = row[0]
        if not isinstance(cfg, dict):
            return {"columns": [], "view_order": [], "default_view": None}
        return {
            "columns": cfg.get("columns", []) or [],
            "view_order": cfg.get("view_order", []) or [],
            "default_view": cfg.get("default_view"),
        }


    async def get_schema(self, workspace_id: UUID, table_id: str) -> list[dict[str, Any]]:
        """Return the columns array from public.table_schemas.config."""
        result = await self.session.execute(
            sa_text(
                "SELECT config -> 'columns' FROM public.table_schemas "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        if not row or row[0] is None:
            return []
        cols = row[0]
        return cols if isinstance(cols, list) else []

    async def get_default_view_name(self, workspace_id: UUID, table_id: str) -> str | None:
        result = await self.session.execute(
            sa_text(
                "SELECT config ->> 'default_view' FROM public.table_schemas "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        return row[0] if row and row[0] else None

    async def get_order(self, workspace_id: UUID, table_id: str) -> list[str]:
        result = await self.session.execute(
            sa_text(
                "SELECT config -> 'view_order' FROM public.table_schemas "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        if not row or row[0] is None:
            return []
        order = row[0]
        return order if isinstance(order, list) else []

    # ── Column CRUD (V46 PG functions) ───────────────────────────────────

    async def add_column(
        self,
        workspace_id: UUID,
        table_id: str,
        name: str,
        col_type: str,
        options: dict[str, Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        """V46 add_column. Always appends to end; call update_col_order
        after if a specific position is needed."""
        result = await self.session.execute(
            sa_text(
                "SELECT add_column(CAST(:ws AS uuid), :tid, :name, :type, "
                "CAST(:options AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": name,
                "type": col_type,
                "options": json.dumps(options),
                "by": str(created_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    async def update_column(
        self,
        workspace_id: UUID,
        table_id: str,
        column_id: str,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT update_column(CAST(:ws AS uuid), :tid, :cid, "
                "CAST(:patch AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "cid": column_id,
                "patch": json.dumps(patch),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    async def delete_column(
        self,
        workspace_id: UUID,
        table_id: str,
        column_id: str,
        updated_by: UUID,
    ) -> None:
        await self.session.execute(
            sa_text(
                "SELECT delete_column(CAST(:ws AS uuid), :tid, :cid, "
                "CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "cid": column_id,
                "by": str(updated_by),
            },
        )
        await self.session.commit()

    async def update_col_order(
        self,
        workspace_id: UUID,
        table_id: str,
        order: list[str],
        updated_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT update_col_order(CAST(:ws AS uuid), :tid, "
                "CAST(:order AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "order": json.dumps(order),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    # ── View order / default view (V46 PG functions) ─────────────────────

    async def set_default_view(
        self,
        workspace_id: UUID,
        table_id: str,
        view_name: str,
        updated_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT update_default_view(CAST(:ws AS uuid), :tid, :name, "
                "CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": view_name,
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()

    async def set_order(
        self,
        workspace_id: UUID,
        table_id: str,
        order: list[str],
        updated_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT update_view_order(CAST(:ws AS uuid), :tid, "
                "CAST(:order AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "order": json.dumps(order),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return result.scalar_one()
