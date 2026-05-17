# src/repository/table_view.py
#
# v40: public.table_views holds user-view rows. PK is
# (workspace_id, table_id, view_id BIGINT). Display name + view type
# live in the `config` JSONB. PG functions V14 own atomic CRUD; this
# repo is a thin pass-through.

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.table_view import TableView


class TableViewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Row access ────────────────────────────────────────────────────────

    async def list_all(self, workspace_id: UUID, table_id: str) -> list[TableView]:
        # populate_existing=True forces SA to overwrite any cached
        # TableView instances in the identity map with fresh DB rows.
        # Without it, after a PG-function UPDATE the session keeps the
        # stale ORM object (expire_on_commit=False) and returns it here
        # — leading to PUT /views/{vid} responses with the OLD config.
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
            ).execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def get_by_id(
        self, workspace_id: UUID, table_id: str, view_id: int
    ) -> TableView | None:
        result = await self.session.execute(
            select(TableView).where(
                TableView.workspace_id == workspace_id,
                TableView.table_id == table_id,
                TableView.view_id == view_id,
            ).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self, workspace_id: UUID, table_id: str, name: str
    ) -> TableView | None:
        result = await self.session.execute(
            sa_text(
                "SELECT * FROM table_views "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid "
                "AND config->>'name' = :name LIMIT 1"
            ),
            {"ws": str(workspace_id), "tid": table_id, "name": name},
        )
        row = result.first()
        if not row:
            return None
        mapping = row._mapping
        return TableView(
            workspace_id=mapping["workspace_id"],
            table_id=mapping["table_id"],
            view_id=mapping["view_id"],
            config=mapping["config"],
            created_by=mapping.get("created_by"),
            updated_by=mapping.get("updated_by"),
            created_at=mapping["created_at"],
            updated_at=mapping["updated_at"],
        )

    # ── User-view CRUD (V14 PG functions) ─────────────────────────────────

    async def create_view(
        self,
        workspace_id: UUID,
        table_id: str,
        config: dict[str, Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        """V14 create_view: inserts the row and appends view_id to
        table_schemas.config.view_order atomically. Returns the full
        schema snapshot {columns, view_order, default_view, views}."""
        await self.session.execute(
            sa_text(
                "SELECT create_view(CAST(:ws AS uuid), :tid, "
                "CAST(:config AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "config": json.dumps(config),
                "by": str(created_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def update_view(
        self,
        workspace_id: UUID,
        table_id: str,
        view_id: int,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        """V14 update_view: shallow-merges `patch` into the row's
        config. Returns the full schema snapshot with the embedded
        views[] array so the FE can replace its store from one shape."""
        await self.session.execute(
            sa_text(
                "SELECT update_view(CAST(:ws AS uuid), :tid, :vid, "
                "CAST(:patch AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "vid": view_id,
                "patch": json.dumps(patch),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def delete_view(
        self,
        workspace_id: UUID,
        table_id: str,
        view_id: int,
        deleted_by: UUID,
    ) -> dict[str, Any]:
        """V14 delete_view: removes the row + strips view_id from
        view_order. Returns the full schema snapshot."""
        await self.session.execute(
            sa_text(
                "SELECT delete_view(CAST(:ws AS uuid), :tid, :vid, "
                "CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "vid": view_id,
                "by": str(deleted_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    # ── Schema reads (table_schemas) ──────────────────────────────────────

    async def get_tables_schema(
        self, workspace_id: UUID, table_id: str
    ) -> dict[str, Any]:
        """Return the entire schema snapshot the FE needs to render a
        table: {columns, view_order, default_view, views}. Used by GET
        and every mutation endpoint (server-is-SSOT)."""
        result = await self.session.execute(
            sa_text(
                "SELECT config FROM public.table_schemas "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        cfg: dict[str, Any] = {}
        if row and isinstance(row[0], dict):
            cfg = row[0]
        view_order = cfg.get("view_order", []) or []
        views_rows = await self.list_all(workspace_id, table_id)
        by_id: dict[int, dict[str, Any]] = {
            v.view_id: {
                "view_id": v.view_id,
                "name": v.name,
                "type": v.type,
                "config": v.config,
            }
            for v in views_rows
        }
        ordered_views = [by_id[i] for i in view_order if i in by_id]
        leftover = [d for i, d in by_id.items() if i not in view_order]
        return {
            "columns": cfg.get("columns", []) or [],
            "view_order": view_order,
            "default_view": cfg.get("default_view"),
            "views": ordered_views + leftover,
        }

    # ── Order / default-view / column writes (V13 + V14 PG functions) ─────

    async def set_order(
        self,
        workspace_id: UUID,
        table_id: str,
        view_order: list[int],
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
                "order": json.dumps(view_order),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def set_default_view(
        self,
        workspace_id: UUID,
        table_id: str,
        view_id: int | None,
        updated_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT update_default_view(CAST(:ws AS uuid), :tid, "
                ":vid, CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "vid": view_id,
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def update_col_order(
        self,
        workspace_id: UUID,
        table_id: str,
        col_order: list[str],
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
                "order": json.dumps(col_order),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def add_column(
        self,
        workspace_id: UUID,
        table_id: str,
        name: str,
        col_type: str,
        options: dict[str, Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT add_column(CAST(:ws AS uuid), :tid, :name, :type, "
                "CAST(:opts AS jsonb), CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "name": name,
                "type": col_type,
                "opts": json.dumps(options),
                "by": str(created_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def update_column(
        self,
        workspace_id: UUID,
        table_id: str,
        column_id: str,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        # V13 update_column takes column_id as TEXT (not UUID) — it indexes
        # into the columns JSONB array by string match on column_id.
        result = await self.session.execute(
            sa_text(
                "SELECT update_column(CAST(:ws AS uuid), :tid, "
                ":cid, CAST(:patch AS jsonb), CAST(:by AS uuid))"
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
        return await self.get_tables_schema(workspace_id, table_id)

    async def delete_column(
        self,
        workspace_id: UUID,
        table_id: str,
        column_id: str,
        deleted_by: UUID,
    ) -> dict[str, Any]:
        result = await self.session.execute(
            sa_text(
                "SELECT delete_column(CAST(:ws AS uuid), :tid, "
                ":cid, CAST(:by AS uuid))"
            ),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "cid": column_id,
                "by": str(deleted_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)
