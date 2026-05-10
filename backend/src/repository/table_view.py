# src/repository/table_view.py
# V34: One row per piece of table metadata.
#   - __schema__ row holds the column array
#   - __order__ row holds the ordered name array
#   - user-named rows hold view configs
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
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
        config: dict[str, Any] | list[Any],
        created_by: UUID | None = None,
    ) -> TableView:
        # Use raw SQL to avoid session.refresh() after commit — same pattern as update().
        # session.refresh() can raise InvalidRequestError on detached instances when the
        # session has prior raw-SQL commits (e.g. set_schema → create_column_index → create).
        cb = str(created_by) if created_by else None
        await self.session.execute(
            sa_text(
                "INSERT INTO table_views "
                "(workspace_id, table_id, name, type, config, created_by, updated_by) "
                "VALUES (CAST(:ws AS uuid), :tid, :name, :type, CAST(:config AS jsonb), "
                "CAST(:cb AS uuid), CAST(:cb AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": name,
                "type": view_type,
                "config": json.dumps(config),
                "cb": cb,
            },
        )
        await self.session.commit()
        result = await self.session.execute(
            sa_text(
                "SELECT workspace_id, table_id, name, type, config, is_default, "
                "created_by, updated_by, created_at, updated_at "
                "FROM table_views "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid AND name = :name"
            ),
            {"ws": str(workspace_id), "tid": table_id, "name": name},
        )
        row = result.mappings().one()
        return TableView(
            workspace_id=row["workspace_id"],
            table_id=row["table_id"],
            name=row["name"],
            type=row["type"],
            config=row["config"],
            is_default=row["is_default"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def update(self, view: TableView, updates: dict[str, Any]) -> TableView:
        # Capture original PK before any mutation; view may be detached from session.
        ws = str(view.workspace_id)
        tid = view.table_id
        original_name = view.name

        set_parts: list[str] = []
        params: dict[str, Any] = {"ws": ws, "tid": tid, "orig_name": original_name}

        if "config" in updates:
            set_parts.append("config = CAST(:config AS jsonb)")
            params["config"] = json.dumps(updates["config"])
        if "name" in updates:
            set_parts.append("name = :new_name")
            params["new_name"] = updates["name"]
        if "type" in updates:
            set_parts.append("type = :type")
            params["type"] = updates["type"]
        if "updated_by" in updates:
            set_parts.append("updated_by = :updated_by")
            params["updated_by"] = str(updates["updated_by"]) if updates["updated_by"] else None

        set_parts.append("updated_at = NOW()")

        await self.session.execute(
            sa_text(
                f"UPDATE table_views SET {', '.join(set_parts)} "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid AND name = :orig_name"
            ),
            params,
        )
        await self.session.commit()

        new_name = str(updates.get("name", original_name))
        result = await self.session.execute(
            sa_text(
                "SELECT workspace_id, table_id, name, type, config, is_default, "
                "created_by, updated_by, created_at, updated_at "
                "FROM table_views "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid AND name = :name"
            ),
            {"ws": ws, "tid": tid, "name": new_name},
        )
        row = result.mappings().one()
        return TableView(
            workspace_id=row["workspace_id"],
            table_id=row["table_id"],
            name=row["name"],
            type=row["type"],
            config=row["config"],
            is_default=row["is_default"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def delete(self, view: TableView) -> None:
        await self.session.delete(view)
        await self.session.commit()

    # ── User views (excludes schema + order rows) ────────────────────────

    async def list_user_views(self, workspace_id: UUID, table_id: str) -> list[TableView]:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.type.in_(USER_VIEW_TYPES),  # type: ignore[attr-defined]
            )
        )
        return list(result.scalars().all())

    # ── __schema__ row helpers ───────────────────────────────────────────

    async def get_schema(self, workspace_id: UUID, table_id: str) -> list[dict[str, Any]]:
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

    # ── Default view (V37 is_default flag) ────────────────────────────────

    async def get_default_view_name(self, workspace_id: UUID, table_id: str) -> str | None:
        """Return the name of the default view, or None if none is marked."""
        from sqlalchemy import text

        result = await self.session.execute(
            text(
                "SELECT name FROM public.table_views WHERE workspace_id = :ws AND table_id = :tid AND is_default"
            ).bindparams(ws=workspace_id, tid=table_id)
        )
        row = result.first()
        return row[0] if row else None

    async def set_default_view(self, workspace_id: UUID, table_id: str, view_name: str) -> None:
        """Atomically flip the default view via the SQL helper."""
        from sqlalchemy import text

        await self.session.execute(
            text("SELECT set_table_default_view(:ws, :tid, :name)").bindparams(
                ws=workspace_id, tid=table_id, name=view_name
            )
        )
        await self.session.commit()

    # ── __order__ row helpers ────────────────────────────────────────────

    async def get_order(self, workspace_id: UUID, table_id: str) -> list[str]:
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
