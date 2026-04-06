# router/api/tables.py

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.table import Table, TableCreate, TableResponse, TableUpdate
from models.user import User
from repository.table import TableRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(prefix="/tables", tags=["tables"])


async def _get_table_for_member(
    table_id: str,
    user: User,
    session: AsyncSession,
) -> Table:
    """Fetch table by UUID or name and verify the current user is a member of its workspace."""
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


# --------------------------------------------------
# TABLES
# --------------------------------------------------


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new table in the specified workspace (or user's first workspace)"""
    ws_repo = WorkspaceRepository(session)
    if data.workspace_id:
        workspace = await ws_repo.resolve_workspace(data.workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if not await ws_repo.is_member(workspace.workspace_id, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of that workspace")
        workspace_id = workspace.workspace_id
    else:
        workspace = await ws_repo.get_first_owned_workspace(user.user_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No workspace found — create a workspace first"
            )
        workspace_id = workspace.workspace_id
    table_repo = TableRepository(session)
    return await table_repo.create(workspace_id=workspace_id, name=data.name)


@router.get("", response_model=list[TableResponse])
async def list_tables(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all tables across workspaces the current user is a member of"""
    ws_repo = WorkspaceRepository(session)
    workspaces = await ws_repo.list_by_user(user.user_id)
    table_repo = TableRepository(session)
    tables: list[Table] = []
    for ws in workspaces:
        tables.extend(await table_repo.list_by_workspace(ws.workspace_id))
    return tables


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a table by ID (user must be a workspace member)"""
    return await _get_table_for_member(table_id, user, session)


@router.put("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: str,
    data: TableUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a table name (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    existing = await table_repo.list_by_workspace(table.workspace_id)
    if any(t.name == data.name and t.table_id != table.table_id for t in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A table with that name already exists in this workspace"
        )
    return await table_repo.update(table, data.name)


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a table (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    await table_repo.delete(table)


# --------------------------------------------------
# COLUMNS (stored in tables.columns JSONB)
# --------------------------------------------------


@router.get("/{table_id}/columns")
async def list_columns(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List columns for a table (sorted by position)"""
    table = await _get_table_for_member(table_id, user, session)
    return sorted(table.columns, key=lambda c: c.get("position", 0))


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a column to a table"""
    table = await _get_table_for_member(table_id, user, session)
    column_dict: dict[str, Any] = {
        "column_id": str(uuid4()),
        "name": data.get("name", ""),
        "type": data.get("type", "text"),
        "options": data.get("options", {}),
        "position": data.get("position", len(table.columns)),
        "created_at": datetime.utcnow().isoformat(),
    }
    table_repo = TableRepository(session)
    updated = await table_repo.add_column(table, column_dict)
    await table_repo.create_column_index(table.table_id, column_dict["column_id"], column_dict["type"])
    return updated.columns[-1]


@router.put("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: str,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a column in the table's columns JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(c.get("column_id") == column_id for c in table.columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    # strip immutable fields from updates
    updates = {k: v for k, v in data.items() if k not in ("column_id", "created_at")}
    table_repo = TableRepository(session)
    # If type changed, recreate index
    if "type" in updates:
        old_col = next(c for c in table.columns if c.get("column_id") == column_id)
        if updates["type"] != old_col.get("type"):
            await table_repo.drop_column_index(table.table_id, column_id)
            await table_repo.create_column_index(table.table_id, column_id, updates["type"])
    updated = await table_repo.update_column(table, column_id, updates)
    col = next(c for c in updated.columns if c.get("column_id") == column_id)
    return col


@router.delete("/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: str,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a column from the table's columns JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(c.get("column_id") == column_id for c in table.columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    table_repo = TableRepository(session)
    await table_repo.drop_column_index(table.table_id, column_id)
    await table_repo.delete_column(table, column_id)


# --------------------------------------------------
# VIEWS (stored in tables.views JSONB)
# --------------------------------------------------


@router.get("/{table_id}/views")
async def list_views(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List views for a table"""
    table = await _get_table_for_member(table_id, user, session)
    return table.views


@router.post("/{table_id}/views", status_code=status.HTTP_201_CREATED)
async def create_view(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a view to a table"""
    table = await _get_table_for_member(table_id, user, session)
    name = data.get("name", "")
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="View name is required")
    if any(v.get("name") == name for v in table.views):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
    view_dict: dict[str, Any] = {
        "name": name,
        "type": data.get("type", "table"),
        "config": data.get("config", {}),
    }
    table_repo = TableRepository(session)
    updated = await table_repo.add_view(table, view_dict)
    return updated.views[-1]


@router.put("/{table_id}/views/{view_name}")
async def update_view(
    table_id: str,
    view_name: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a view's config in the table's views JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(v.get("name") == view_name for v in table.views):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    updates = {k: v for k, v in data.items() if k != "name"}
    table_repo = TableRepository(session)
    updated = await table_repo.update_view(table, view_name, updates)
    return next(v for v in updated.views if v.get("name") == view_name)


@router.delete("/{table_id}/views/{view_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    table_id: str,
    view_name: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove a view from the table's views JSONB array"""
    table = await _get_table_for_member(table_id, user, session)
    if not any(v.get("name") == view_name for v in table.views):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    table_repo = TableRepository(session)
    await table_repo.delete_view(table, view_name)


# --------------------------------------------------
# PM TEMPLATE
# --------------------------------------------------

_PM_COLUMNS: list[dict[str, Any]] = [
    {"name": "Title", "type": "text"},
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
    {"name": "Doc", "type": "url"},
    {"name": "Parent", "type": "text"},
]


@router.post("/template/pm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_pm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a PM project table with pre-configured columns and default views"""
    name = data.get("name", "")
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
    ws_repo = WorkspaceRepository(session)
    raw_workspace_id = data.get("workspace_id")
    if raw_workspace_id:
        workspace = await ws_repo.resolve_workspace(str(raw_workspace_id))
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if not await ws_repo.is_member(workspace.workspace_id, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of that workspace")
        workspace_id = workspace.workspace_id
    else:
        workspace = await ws_repo.get_first_owned_workspace(user.user_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No workspace found — create a workspace first"
            )
        workspace_id = workspace.workspace_id

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, name=name)

    # Add columns and collect their generated IDs for view config
    col_ids: dict[str, str] = {}
    for pos, col_def in enumerate(_PM_COLUMNS):
        column_dict: dict[str, Any] = {
            "column_id": str(uuid4()),
            "name": col_def["name"],
            "type": col_def["type"],
            "options": col_def.get("options", {}),
            "position": pos,
            "created_at": datetime.utcnow().isoformat(),
        }
        table = await table_repo.add_column(table, column_dict)
        await table_repo.create_column_index(table.table_id, column_dict["column_id"], column_dict["type"])
        col_ids[col_def["name"]] = column_dict["column_id"]

    # Default views
    status_col_id = col_ids.get("Status", "")
    start_col_id = col_ids.get("Start Date", "")
    due_col_id = col_ids.get("Due Date", "")

    default_views: list[dict[str, Any]] = [
        {"name": "Table", "type": "table", "config": {"sort": {"colId": start_col_id, "dir": "desc"}}},
        {
            "name": "Sprint Board",
            "type": "kanban",
            "config": {
                "group_by": status_col_id,
                "card_fields": [
                    col_ids.get("Title", ""),
                    col_ids.get("Priority", ""),
                    col_ids.get("Assignee", ""),
                ],
            },
        },
        {
            "name": "Roadmap",
            "type": "timeline",
            "config": {
                "start_col": start_col_id,
                "end_col": due_col_id,
                "color_by": status_col_id,
                "group_by": col_ids.get("Type", ""),
            },
        },
    ]
    for view_dict in default_views:
        table = await table_repo.add_view(table, view_dict)

    return table
