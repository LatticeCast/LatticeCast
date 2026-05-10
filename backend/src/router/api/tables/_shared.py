from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

_PM_COLUMNS: list[dict[str, Any]] = [
    {"name": "Title", "type": "text"},
    {"name": "Doc", "type": "doc"},
    {
        "name": "Type",
        "type": "select",
        "options": {
            "choices": [
                {"value": "epic", "color": "bg-purple-100 text-purple-700"},
                {"value": "story", "color": "bg-blue-100 text-blue-700"},
                {"value": "task", "color": "bg-green-100 text-green-700"},
                {"value": "bug", "color": "bg-red-100 text-red-700"},
            ]
        },
    },
    {
        "name": "Status",
        "type": "select",
        "options": {
            "choices": [
                {"value": "todo", "color": "bg-gray-100 text-gray-700"},
                {"value": "in_progress", "color": "bg-blue-100 text-blue-700"},
                {"value": "testing", "color": "bg-purple-100 text-purple-700"},
                {"value": "debugging", "color": "bg-red-100 text-red-700"},
                {"value": "review", "color": "bg-yellow-100 text-yellow-700"},
                {"value": "done", "color": "bg-green-100 text-green-700"},
                {"value": "merged", "color": "bg-emerald-100 text-emerald-700"},
            ]
        },
    },
    {
        "name": "Priority",
        "type": "select",
        "options": {
            "choices": [
                {"value": "critical", "color": "bg-red-100 text-red-700"},
                {"value": "high", "color": "bg-orange-100 text-orange-700"},
                {"value": "medium", "color": "bg-yellow-100 text-yellow-700"},
                {"value": "low", "color": "bg-gray-100 text-gray-700"},
            ]
        },
    },
    {"name": "Assignee", "type": "text"},
    {"name": "Start Date", "type": "date"},
    {"name": "Due Date", "type": "date"},
    {"name": "Estimate", "type": "number"},
    {"name": "Tags", "type": "tags"},
    {"name": "Description", "type": "text"},
    {"name": "Parent", "type": "text"},
]

_CRM_COLUMNS: list[dict[str, Any]] = [
    {"name": "Title", "type": "text"},
    {"name": "Doc", "type": "doc"},
    {
        "name": "Stage",
        "type": "select",
        "options": {
            "choices": [
                {"value": "lead", "color": "bg-gray-100 text-gray-700"},
                {"value": "qualified", "color": "bg-blue-100 text-blue-700"},
                {"value": "proposal", "color": "bg-yellow-100 text-yellow-700"},
                {"value": "won", "color": "bg-green-100 text-green-700"},
                {"value": "lost", "color": "bg-red-100 text-red-700"},
            ]
        },
    },
    {"name": "Value", "type": "number"},
    {"name": "Owner", "type": "text"},
    {"name": "Close Date", "type": "date"},
    {"name": "Tags", "type": "tags"},
    {"name": "Description", "type": "text"},
]


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
