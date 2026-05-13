from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

# V38: template column lists moved into _build_template_columns() inside
# the create_table_from_template PG function. Python-side definitions
# removed to keep one source of truth.


async def _get_table_for_member(
    table_id: str,
    user: User,
    session: AsyncSession,
) -> Table:
    ws_repo = WorkspaceRepository(session)
    workspaces = await ws_repo.list_by_user(user.user_id)
    workspace_ids = [ws.workspace_id for ws in workspaces]
    table_repo = TableRepository(session)
    table = await table_repo.resolve_table_global(table_id, workspace_ids)
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    if not await ws_repo.is_member(table.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


async def _build_table_response(table: Table, session: AsyncSession) -> dict[str, Any]:
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    default_view = await view_repo.get_default_view_name(table.workspace_id, table.table_id)
    return {
        "workspace_id": table.workspace_id,
        "table_id": table.table_id,
        "columns": sorted(columns, key=lambda c: c.get("position", 0)),
        "default_view": default_view,
        "created_at": table.created_at,
        "updated_at": table.updated_at,
    }
