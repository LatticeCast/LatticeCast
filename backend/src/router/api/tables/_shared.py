from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository

# V38: template column lists moved into _build_template_columns() inside
# the create_table_from_template PG function. Python-side definitions
# removed to keep one source of truth.


async def _get_table_for_member(
    table_id: int,
    user: User,
    session: AsyncSession,
    workspace_id: UUID | None = None,
) -> Table:
    """Resolve a table the caller can reach, or raise 404.

    table_id is the table's identity now, so the lookup is a primary-key read
    and no longer ambiguous across workspaces. `workspace_id` is still accepted
    by callers that keep it in the URL, but it only narrows an already unique
    row.

    Authorization is RLS's alone: the tables_read policy already limits the
    resolve to readable workspaces, so a table in an unreachable workspace
    and a table that does not exist are indistinguishable here. Both raise
    404, which is what keeps existence undisclosed.
    """
    table_repo = TableRepository(session)
    table = await table_repo.get(table_id)
    if table is None or (workspace_id is not None and table.workspace_id != workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


async def _build_table_response(table: Table, session: AsyncSession) -> dict[str, Any]:
    """Returns table identity + full schema snapshot. Includes
    {columns, view_order, default_view, views} — same shape every
    mutation endpoint returns. FE never needs separate read calls."""
    view_repo = TableViewRepository(session)
    schema = await view_repo.get_tables_schema(table.workspace_id, table.table_id)
    return {
        "workspace_id": table.workspace_id,
        "table_id": table.table_id,
        "table_name": table.table_name,
        "columns": schema.get("columns", []),
        "view_order": schema.get("view_order", []),
        "default_view": schema.get("default_view", 0) or 0,
        "views": schema.get("views", []),
        "created_at": table.created_at,
        "updated_at": table.updated_at,
    }
