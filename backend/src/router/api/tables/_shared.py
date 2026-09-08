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
    table_id: str,
    user: User,
    session: AsyncSession,
    workspace_id: UUID | None = None,
) -> Table:
    """Resolve a table the caller can reach, or raise 404.

    table_id is unique only WITHIN a workspace — different workspaces may
    each have a table with the same string id (e.g. two users both have
    `articles`). When the caller knows the workspace (URL like
    /{workspace_id}/{table_id}), pass `workspace_id` to scope the lookup
    unambiguously. When omitted, we search every workspace the caller may
    read and pick the first match — fine for the rare case where only the
    table_id is known, but ambiguous when names collide.

    Authorization is RLS's alone: the tables_read policy already limits the
    resolve to readable workspaces, so a table in an unreachable workspace
    and a table that does not exist are indistinguishable here. Both raise
    404, which is what keeps existence undisclosed.
    """
    table_repo = TableRepository(session)
    scope = [workspace_id] if workspace_id is not None else None
    table = await table_repo.resolve_table_global(table_id, scope)
    if not table:
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
        "columns": schema.get("columns", []),
        "view_order": schema.get("view_order", []),
        "default_view": schema.get("default_view", 0) or 0,
        "views": schema.get("views", []),
        "created_at": table.created_at,
        "updated_at": table.updated_at,
    }
