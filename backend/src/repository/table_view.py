# src/repository/table_view.py
#
# v40: public.table_views holds user-view rows. PK is
# (table_id, view_id BIGINT). The workspace belongs to the parent table,
# so a view does not carry a copy. Display name + view type live in the
# `config` JSONB. PG functions V14 own atomic CRUD; this repo is a thin
# pass-through.

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.db import reapply_rls_context
from models.table_view import TableView


def schema_from_config(config: dict[str, Any], views_rows: list[TableView]) -> dict[str, Any]:
    """Assemble the same schema for a single table or a batched list."""
    view_order = config.get("view_order", []) or []
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
    leftover = [value for i, value in by_id.items() if i not in view_order]
    return {
        "columns": config.get("columns", []) or [],
        "view_order": view_order,
        "default_view": config.get("default_view", 0) or 0,
        "views": ordered_views + leftover,
        "view_config": config.get("view_config", {}) or {},
    }


class TableViewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Row access ────────────────────────────────────────────────────────

    async def list_all(self, table_id: int) -> list[TableView]:
        await reapply_rls_context(self.session)
        # populate_existing=True forces SA to overwrite any cached
        # TableView instances in the identity map with fresh DB rows.
        # Without it, after a PG-function UPDATE the session keeps the
        # stale ORM object (expire_on_commit=False) and returns it here
        # — leading to PUT /views/{vid} responses with the OLD config.
        result = await self.session.execute(
            select(TableView)
            .where(
                TableView.table_id == table_id,
            )
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def list_for_tables(self, table_ids: list[int]) -> list[TableView]:
        """Read views for all visible tables with one RLS-scoped query."""
        if not table_ids:
            return []
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(TableView)
            .where(TableView.table_id.in_(table_ids))
            .order_by(TableView.table_id, TableView.view_id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def get_by_id(self, table_id: int, view_id: int) -> TableView | None:
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(TableView)
            .where(
                TableView.table_id == table_id,
                TableView.view_id == view_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, table_id: int, name: str) -> TableView | None:
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            sa_text("SELECT * FROM table_views WHERE table_id = :tid AND config->>'name' = :name LIMIT 1"),
            {"tid": table_id, "name": name},
        )
        row = result.first()
        if not row:
            return None
        mapping = row._mapping
        return TableView(
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
        table_id: int,
        config: dict[str, Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        """V14 create_view: inserts the row and appends view_id to
        tables.config.view_order atomically. Returns the full
        schema snapshot {columns, view_order, default_view, views}."""
        await self.session.execute(
            sa_text("SELECT create_view(CAST(:ws AS uuid), :tid, CAST(:config AS jsonb), CAST(:by AS uuid))"),
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
        table_id: int,
        view_id: int,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        """V14 update_view: shallow-merges `patch` into the row's
        config. Returns the full schema snapshot with the embedded
        views[] array so the FE can replace its store from one shape."""
        await self.session.execute(
            sa_text("SELECT update_view(CAST(:ws AS uuid), :tid, :vid, CAST(:patch AS jsonb), CAST(:by AS uuid))"),
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
        table_id: int,
        view_id: int,
        deleted_by: UUID,
    ) -> dict[str, Any]:
        """V14 delete_view: removes the row + strips view_id from
        view_order. Returns the full schema snapshot."""
        await self.session.execute(
            sa_text("SELECT delete_view(CAST(:ws AS uuid), :tid, :vid, CAST(:by AS uuid))"),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "vid": view_id,
                "by": str(deleted_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    # ── Schema reads (tables.config) ──────────────────────────────────────

    async def get_tables_schema(self, workspace_id: UUID, table_id: int) -> dict[str, Any]:
        """Return the entire schema snapshot the FE needs to render a
        table: {columns, view_order, default_view, views}. Used by GET
        and every mutation endpoint (server-is-SSOT)."""
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            sa_text("SELECT config FROM public.tables WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"),
            {"ws": str(workspace_id), "tid": table_id},
        )
        row = result.first()
        cfg: dict[str, Any] = {}
        if row and isinstance(row[0], dict):
            cfg = row[0]
        return schema_from_config(cfg, await self.list_all(table_id))

    # ── Order / default-view / column writes (V13 + V14 PG functions) ─────

    async def set_order(
        self,
        workspace_id: UUID,
        table_id: int,
        view_order: list[int],
        updated_by: UUID,
    ) -> dict[str, Any]:
        await self.session.execute(
            sa_text("SELECT update_view_order(CAST(:ws AS uuid), :tid, CAST(:order AS jsonb), CAST(:by AS uuid))"),
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
        table_id: int,
        view_id: int | None,
        updated_by: UUID,
    ) -> dict[str, Any]:
        await self.session.execute(
            sa_text("SELECT update_default_view(CAST(:ws AS uuid), :tid, :vid, CAST(:by AS uuid))"),
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
        table_id: int,
        col_order: list[str],
        updated_by: UUID,
    ) -> dict[str, Any]:
        await self.session.execute(
            sa_text("SELECT update_col_order(CAST(:ws AS uuid), :tid, CAST(:order AS jsonb), CAST(:by AS uuid))"),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "order": json.dumps(col_order),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def update_view_config(
        self,
        workspace_id: UUID,
        table_id: int,
        view_config: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        """Replace tables.config.view_config wholesale — the implicit Schema
        tab's counterpart to update_view() for real views.

        No PG function, no server-side merge: the FE already sends the full
        desired object (it builds it from the current value plus its own
        change before calling this), same as table.py's plain-SQL rename.
        A server-side partial merge would be redundant here — view_config
        is never queried through JSONB operators, just read/written whole —
        and would actively break clearing a field: a cleared key is absent
        from the FE's JSON (JSON.stringify drops `undefined`), so a merge
        that only deletes on explicit `null` would silently keep the stale
        value forever.
        """
        await self.session.execute(
            sa_text("""
                UPDATE public.tables
                SET    config = jsonb_set(config, '{view_config}', CAST(:view_config AS jsonb)),
                       updated_by = :by,
                       updated_at = now()
                WHERE  workspace_id = CAST(:ws AS uuid)
                AND    table_id     = :tid
            """),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "view_config": json.dumps(view_config),
                "by": str(updated_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)

    async def add_column(
        self,
        workspace_id: UUID,
        table_id: int,
        name: str,
        col_type: str,
        options: dict[str, Any],
        created_by: UUID,
    ) -> dict[str, Any]:
        await self.session.execute(
            sa_text(
                "SELECT add_column(CAST(:ws AS uuid), :tid, :name, :type, CAST(:opts AS jsonb), CAST(:by AS uuid))"
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
        table_id: int,
        column_id: str,
        patch: dict[str, Any],
        updated_by: UUID,
    ) -> dict[str, Any]:
        # V13 update_column takes column_id as TEXT (not UUID) — it indexes
        # into the columns JSONB array by string match on column_id.
        await self.session.execute(
            sa_text("SELECT update_column(CAST(:ws AS uuid), :tid, :cid, CAST(:patch AS jsonb), CAST(:by AS uuid))"),
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
        table_id: int,
        column_id: str,
        deleted_by: UUID,
    ) -> dict[str, Any]:
        await self.session.execute(
            sa_text("SELECT delete_column(CAST(:ws AS uuid), :tid, :cid, CAST(:by AS uuid))"),
            {
                "ws": str(workspace_id),
                "tid": table_id,
                "cid": column_id,
                "by": str(deleted_by),
            },
        )
        await self.session.commit()
        return await self.get_tables_schema(workspace_id, table_id)
