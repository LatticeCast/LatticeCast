# src/repository/table.py
# V34: Table holds identity only. Column CRUD lives in TableViewRepository
# (operating on the __schema__ row). Index management stays here because it
# touches public.rows, not table_views.
import hashlib
import re
from datetime import datetime
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

    async def create_from_template(
        self,
        workspace_id: UUID,
        table_id: str,
        kind: str,
        created_by: UUID,
    ) -> Table:
        """V38: Atomic table create + populate via the PG function
        `create_table_from_template`. One transaction covers the INSERT,
        the __schema__ + __order__ writes, per-column index creation, and
        (for templates) the seed views and default-view flag."""
        tid = table_id.lower()
        await self.session.execute(
            text(
                "SELECT create_table_from_template("
                "CAST(:ws AS uuid), :tid, :kind, CAST(:by AS uuid))"
            ),
            {"ws": str(workspace_id), "tid": tid, "kind": kind, "by": str(created_by)},
        )
        await self.session.commit()
        result = await self.session.execute(
            text(
                "SELECT workspace_id, table_id, created_at, updated_at FROM tables "
                "WHERE workspace_id = CAST(:ws AS uuid) AND table_id = :tid"
            ),
            {"ws": str(workspace_id), "tid": tid},
        )
        row = result.mappings().one()
        return Table(
            workspace_id=row["workspace_id"],
            table_id=row["table_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

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
        """Resolve a table by case-insensitive name across the given workspaces."""
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
        await self.session.refresh(table)  # refreshes attached instance — safe
        return table

    async def delete(self, table: Table) -> None:
        await self.session.delete(table)
        await self.session.commit()

    # ── Per-column index management (PG-side via SECURITY DEFINER funcs) ──

    def _index_name(self, table_id: str, column_id: str) -> str:
        # create_row_data_index validates ^idx_rd_[a-zA-Z0-9_]+$, so non-ASCII
        # table_ids (e.g. Chinese "出國") would explode. Fall back to a hash
        # when the table_id contains anything outside [A-Za-z0-9_-].
        ascii_tid = re.sub(r"[^A-Za-z0-9_]", "", table_id.replace("-", ""))
        if not ascii_tid or ascii_tid != table_id.replace("-", ""):
            ascii_tid = hashlib.sha1(table_id.encode("utf-8")).hexdigest()[:12]
        else:
            ascii_tid = ascii_tid[:12]
        cid = column_id.replace("-", "")[:12]
        return f"idx_rd_{ascii_tid}_{cid}"

    async def create_column_index(self, table_id: str, column_id: str, col_type: str) -> None:
        """app_user has no DDL — V27 defines create_row_data_index as
        SECURITY DEFINER owned by dba; we call it via SELECT."""
        if col_type not in BTREE_TYPES and col_type not in GIN_TYPES:
            return
        idx_name = self._index_name(table_id, column_id)
        await self.session.execute(
            text("SELECT create_row_data_index(:idx, :tid, :cid, :ct)").bindparams(
                idx=idx_name, tid=str(table_id), cid=column_id, ct=col_type
            )
        )
        await self.session.commit()

    async def drop_column_index(self, table_id: str, column_id: str) -> None:
        idx_name = self._index_name(table_id, column_id)
        await self.session.execute(text("SELECT drop_row_data_index(:idx)").bindparams(idx=idx_name))
        await self.session.commit()
