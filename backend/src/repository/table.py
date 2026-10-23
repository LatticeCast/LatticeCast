# src/repository/table.py
# V34: Table holds identity only. Column CRUD lives in TableViewRepository
# (operating on the __schema__ row). Index management stays here because it
# touches public.rows, not table_views.
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import reapply_rls_context
from models.table import Table

# Column types that carry a per-column partial index on public.rows. This list
# must match the types public.create_row_data_index accepts, or a column type
# here is rejected by the database and one missing here silently has no index.
INDEXED_TYPES = {
    "number",
    "date",
    "datetime",
    "text",
    "string",
    "select",
    "tags",
    "email",
    "url",
    "phone",
    "checkbox",
}


class TableRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_from_template(
        self,
        workspace_id: UUID,
        table_name: str,
        kind: str,
        created_by: UUID,
    ) -> Table:
        """V38: Atomic table create + populate via the PG function
        `create_table_from_template`. One transaction covers the INSERT,
        the __schema__ + __order__ writes, per-column index creation, and
        (for templates) the seed views and default-view flag.

        The identity is the database's to assign; the caller only names the
        table, so the new table_id is taken from the function's return value.
        """
        name = table_name.lower()
        result = await self.session.execute(
            text(
                "SELECT create_table_from_template("
                "CAST(:ws AS uuid), :name, :kind, CAST(:by AS uuid)) AS table_id"
            ),
            {"ws": str(workspace_id), "name": name, "kind": kind, "by": str(created_by)},
        )
        new_id = result.scalar_one()
        row_result = await self.session.execute(
            text(
                "SELECT workspace_id, table_id, table_name, created_at, updated_at "
                "FROM tables WHERE table_id = :tid"
            ),
            {"tid": new_id},
        )
        row = row_result.mappings().one()
        await self.session.commit()
        return Table(
            workspace_id=row["workspace_id"],
            table_id=row["table_id"],
            table_name=row["table_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get(self, table_id: int) -> Table | None:
        """Primary-key read. The tables_read policy narrows it to workspaces the
        caller may read, so an unreadable table is indistinguishable from an
        absent one."""
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(Table).where(Table.table_id == table_id)
        )
        return result.scalars().first()

    async def resolve_table_global(
        self, identifier: str, workspace_ids: list[UUID] | None = None
    ) -> Table | None:
        """Resolve a table by name.

        With `workspace_ids`, the search is scoped to those workspaces. With
        None it spans every workspace the caller may read: the tables_read
        policy is already that filter, so no workspace list has to be
        assembled first just to hand it back as a WHERE clause.

        The name is matched exactly: (workspace_id, table_name) is unique, and
        a case-insensitive match would make two tables named `Log` and `log`
        resolve to whichever row the planner returned first.
        """
        await reapply_rls_context(self.session)
        conditions = [Table.table_name == identifier]
        if workspace_ids is not None:
            if not workspace_ids:
                return None
            conditions.append(Table.workspace_id.in_(workspace_ids))
        result = await self.session.execute(
            select(Table).where(*conditions).order_by(Table.table_id)
        )
        return result.scalars().first()

    async def list_by_workspace(self, workspace_id: UUID) -> list[Table]:
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(Table)
            .where(Table.workspace_id == workspace_id)
            .order_by(Table.table_name)
        )
        return list(result.scalars().all())

    async def update(self, table: Table, table_name: str) -> Table:
        """Rename the table. The identity does not move, so nothing cascades."""
        next_table_name = table_name.lower()
        next_updated_at = datetime.now(UTC)
        result = await self.session.execute(
            text("""
                UPDATE tables
                SET table_name = :next_table_name,
                    updated_at = :updated_at
                WHERE table_id = :table_id
                RETURNING workspace_id, table_id, table_name, created_at, updated_at
            """),
            {
                "table_id": table.table_id,
                "next_table_name": next_table_name,
                "updated_at": next_updated_at,
            },
        )
        await self.session.commit()
        updated = result.mappings().one_or_none()
        if updated is None:
            raise RuntimeError("Table disappeared during update")
        return Table(
            workspace_id=updated["workspace_id"],
            table_id=updated["table_id"],
            table_name=updated["table_name"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )

    async def delete(self, table: Table) -> None:
        await self.session.delete(table)
        await self.session.commit()

    # ── Per-column index management (PG-side via SECURITY DEFINER funcs) ──

    @staticmethod
    def _index_name(workspace_id: UUID, table_id: int, column_id: str) -> str:
        """Mirror public._build_rd_idx_name(uuid, bigint, text).

        create_row_data_index rejects a name that does not match the helper's
        answer, so this has to produce exactly the same string:
        idx_rd_<workspace 12 hex>_<table id>_<column 12 hex>.
        """
        ws = str(workspace_id).replace("-", "")[:12]
        cid = column_id.replace("-", "")[:12]
        return f"idx_rd_{ws}_{table_id}_{cid}"

    async def create_column_index(
        self, workspace_id: UUID, table_id: int, column_id: str, col_type: str
    ) -> None:
        """app_user has no DDL — V11 defines create_row_data_index as
        SECURITY DEFINER owned by dba; V18 fixed it to use
        immutable_iso_to_ts() for date columns instead of ::NUMERIC."""
        if col_type not in INDEXED_TYPES:
            return
        idx_name = self._index_name(workspace_id, table_id, column_id)
        await self.session.execute(
            text("SELECT create_row_data_index(:ws, :idx, :tid, :cid, :ct)").bindparams(
                ws=str(workspace_id), idx=idx_name, tid=table_id, cid=column_id, ct=col_type
            )
        )
        await self.session.commit()

    async def drop_column_index(
        self, workspace_id: UUID, table_id: int, column_id: str
    ) -> None:
        idx_name = self._index_name(workspace_id, table_id, column_id)
        await self.session.execute(
            text("SELECT drop_row_data_index(:ws, :idx, :tid, :cid)").bindparams(
                ws=str(workspace_id), idx=idx_name, tid=table_id, cid=column_id
            )
        )
        await self.session.commit()
