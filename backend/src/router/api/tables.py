# router/api/tables.py
# V34: columns live in the __schema__ row of public.table_views; views are
# user-named rows in the same table; display order is the __order__ row.

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import invalidate_schema_cache
from middleware.auth import get_current_user, get_rls_session
from models.table import Table, TableCreate, TableResponse, TableUpdate
from models.table_view import (
    ORDER_ROW_NAME,
    RESERVED_NAMES,
    SCHEMA_ROW_NAME,
    USER_VIEW_TYPES,
)
from models.user import User
from models.view import ViewCreate, validate_view_config
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(prefix="/tables", tags=["tables"])


async def _get_table_for_member(
    table_id: str,
    user: User,
    session: AsyncSession,
) -> Table:
    """Resolve a table the current user is a member of, or 404."""
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
    """Build a TableResponse dict including columns from the __schema__ row."""
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    return {
        "workspace_id": table.workspace_id,
        "table_id": table.table_id,
        "columns": sorted(columns, key=lambda c: c.get("position", 0)),
        "created_at": table.created_at,
        "updated_at": table.updated_at,
    }


# --------------------------------------------------
# TABLES
# --------------------------------------------------


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Create a new table. The DB trigger inserts the __schema__ + __order__
    rows automatically; we then populate the schema with default columns."""
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

    default_cols = [
        {"column_id": str(uuid4()), "name": "Doc", "type": "doc", "options": {}, "position": 0},
        {"column_id": str(uuid4()), "name": "Title", "type": "text", "options": {}, "position": 1},
        {"column_id": str(uuid4()), "name": "Description", "type": "text", "options": {}, "position": 2},
    ]

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, table_id=data.table_id)

    view_repo = TableViewRepository(session)
    await view_repo.set_schema(table.workspace_id, table.table_id, default_cols, updated_by=user.user_id)
    for col in default_cols:
        try:
            await table_repo.create_column_index(table.table_id, col["column_id"], col["type"])
        except Exception:
            pass

    return await _build_table_response(table, session)


@router.get("", response_model=list[TableResponse])
async def list_tables(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List tables across the user's workspaces (each with its column schema)."""
    ws_repo = WorkspaceRepository(session)
    workspaces = await ws_repo.list_by_user(user.user_id)
    table_repo = TableRepository(session)
    out: list[dict[str, Any]] = []
    for ws in workspaces:
        for t in await table_repo.list_by_workspace(ws.workspace_id):
            out.append(await _build_table_response(t, session))
    return out


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    return await _build_table_response(table, session)


@router.put("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: str,
    data: TableUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    existing = await table_repo.list_by_workspace(table.workspace_id)
    if any(t.table_id == data.table_id and t.table_id != table.table_id for t in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A table with that name already exists in this workspace"
        )
    table = await table_repo.update(table, data.table_id)
    return await _build_table_response(table, session)


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    table_repo = TableRepository(session)
    await table_repo.delete(table)


# --------------------------------------------------
# COLUMNS — backed by the __schema__ row's config
# --------------------------------------------------


@router.get("/{table_id}/columns")
async def list_columns(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    return sorted(columns, key=lambda c: c.get("position", 0))


@router.post("/{table_id}/columns", status_code=status.HTTP_201_CREATED)
async def create_column(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    column_dict: dict[str, Any] = {
        "column_id": str(uuid4()),
        "name": data.get("name", ""),
        "type": data.get("type", "text"),
        "options": data.get("options", {}),
        "position": data.get("position", len(columns)),
        "created_at": datetime.utcnow().isoformat(),
    }
    columns = [*columns, column_dict]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    table_repo = TableRepository(session)
    await table_repo.create_column_index(table.table_id, column_dict["column_id"], column_dict["type"])
    await invalidate_schema_cache(str(table.workspace_id))
    return column_dict


@router.put("/{table_id}/columns/{column_id}")
async def update_column(
    table_id: str,
    column_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    if not any(c.get("column_id") == column_id for c in columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")

    updates = {k: v for k, v in data.items() if k not in ("column_id", "created_at")}
    table_repo = TableRepository(session)

    if "type" in updates:
        old_col = next(c for c in columns if c.get("column_id") == column_id)
        if updates["type"] != old_col.get("type"):
            await table_repo.drop_column_index(table.table_id, column_id)
            await table_repo.create_column_index(table.table_id, column_id, updates["type"])

    columns = [{**c, **updates} if c.get("column_id") == column_id else c for c in columns]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    await invalidate_schema_cache(str(table.workspace_id))
    return next(c for c in columns if c.get("column_id") == column_id)


@router.delete("/{table_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    table_id: str,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    columns = await view_repo.get_schema(table.workspace_id, table.table_id)
    if not any(c.get("column_id") == column_id for c in columns):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    table_repo = TableRepository(session)
    await table_repo.drop_column_index(table.table_id, column_id)
    columns = [c for c in columns if c.get("column_id") != column_id]
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    await invalidate_schema_cache(str(table.workspace_id))


# --------------------------------------------------
# VIEWS — user views (excludes __schema__ + __order__)
# --------------------------------------------------


def _view_to_dict(view: Any) -> dict[str, Any]:
    return {
        "name": view.name,
        "type": view.type,
        "config": view.config,
    }


@router.get("/{table_id}/views")
async def list_views(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    """List user views for a table, ordered per __order__ row."""
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    views = await view_repo.list_user_views(table.workspace_id, table.table_id)
    by_name = {v.name: _view_to_dict(v) for v in views}
    order = await view_repo.get_order(table.workspace_id, table.table_id)
    ordered = [by_name[n] for n in order if n in by_name]
    leftover = [d for n, d in by_name.items() if n not in order]
    return ordered + leftover


def _ensure_user_view_name(name: str) -> None:
    if name in RESERVED_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"View name '{name}' is reserved",
        )


def _ensure_user_view_type(view_type: str) -> None:
    if view_type not in USER_VIEW_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"View type must be one of {USER_VIEW_TYPES}",
        )


@router.post("/{table_id}/views", status_code=status.HTTP_201_CREATED)
async def create_view(
    table_id: str,
    data: ViewCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    if not data.name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="View name is required")
    _ensure_user_view_name(data.name)
    _ensure_user_view_type(data.type)
    view_repo = TableViewRepository(session)
    existing = await view_repo.get_by_name(table.workspace_id, table.table_id, data.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
    try:
        validate_view_config(data.type, data.config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    view = await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name=data.name,
        view_type=data.type,
        config=data.config,
        created_by=user.user_id,
    )
    # Append to display order
    order = await view_repo.get_order(table.workspace_id, table.table_id)
    if data.name not in order:
        order = [*order, data.name]
        await view_repo.set_order(table.workspace_id, table.table_id, order, updated_by=user.user_id)
    return _view_to_dict(view)


@router.put("/{table_id}/views/{view_name}")
async def update_view(
    table_id: str,
    view_name: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    _ensure_user_view_name(view_name)
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_name(table.workspace_id, table.table_id, view_name)
    if not view or view.type not in USER_VIEW_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")

    updates: dict[str, Any] = {}
    if "name" in data and data["name"] != view.name:
        new_name = data["name"]
        _ensure_user_view_name(new_name)
        if await view_repo.get_by_name(table.workspace_id, table.table_id, new_name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
        updates["name"] = new_name
    if "type" in data:
        _ensure_user_view_type(data["type"])
        updates["type"] = data["type"]
    if "config" in data:
        updates["config"] = data["config"]
    updates["updated_by"] = user.user_id

    view = await view_repo.update(view, updates)

    # If renamed, swap the name inside __order__
    if "name" in updates:
        order = await view_repo.get_order(table.workspace_id, table.table_id)
        order = [updates["name"] if n == view_name else n for n in order]
        await view_repo.set_order(table.workspace_id, table.table_id, order, updated_by=user.user_id)

    return _view_to_dict(view)


@router.delete("/{table_id}/views/{view_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    table_id: str,
    view_name: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    _ensure_user_view_name(view_name)
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_name(table.workspace_id, table.table_id, view_name)
    if not view or view.type not in USER_VIEW_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    await view_repo.delete(view)
    # Drop from __order__
    order = await view_repo.get_order(table.workspace_id, table.table_id)
    if view_name in order:
        order = [n for n in order if n != view_name]
        await view_repo.set_order(table.workspace_id, table.table_id, order, updated_by=user.user_id)


# --------------------------------------------------
# VIEW ORDER — single PUT replaces the whole order array
# --------------------------------------------------


class ViewOrderRequest(BaseModel):
    order: list[str]


@router.get("/{table_id}/view-order")
async def get_view_order(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[str]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    return await view_repo.get_order(table.workspace_id, table.table_id)


@router.put("/{table_id}/view-order")
async def put_view_order(
    table_id: str,
    data: ViewOrderRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[str]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    # Filter against actual user views to self-heal stale names
    user_view_names = {v.name for v in await view_repo.list_user_views(table.workspace_id, table.table_id)}
    cleaned = [n for n in data.order if n in user_view_names]
    return await view_repo.set_order(table.workspace_id, table.table_id, cleaned, updated_by=user.user_id)


# --------------------------------------------------
# PM TEMPLATE
# --------------------------------------------------

_PM_COLUMNS: list[dict[str, Any]] = [
    {"name": "Doc", "type": "doc"},
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
    {"name": "Parent", "type": "text"},
]


def _build_columns(specs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    columns: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}
    for pos, spec in enumerate(specs):
        col_id = str(uuid4())
        columns.append(
            {
                "column_id": col_id,
                "name": spec["name"],
                "type": spec["type"],
                "options": spec.get("options", {}),
                "position": pos,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        name_to_id[spec["name"]] = col_id
    return columns, name_to_id


async def _resolve_template_workspace(data: dict[str, Any], user: User, ws_repo: WorkspaceRepository):
    raw_workspace = data.get("workspace_name") or data.get("workspace_id")
    if raw_workspace:
        workspace = await ws_repo.resolve_workspace(str(raw_workspace))
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if not await ws_repo.is_member(workspace.workspace_id, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of that workspace")
        return workspace.workspace_id
    workspace = await ws_repo.get_first_owned_workspace(user.user_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No workspace found — create a workspace first"
        )
    return workspace.workspace_id


@router.post("/template/pm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_pm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table_id = data.get("table_id", "") or data.get("table_name", "") or data.get("name", "")
    if not table_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="table_id is required")
    ws_repo = WorkspaceRepository(session)
    workspace_id = await _resolve_template_workspace(data, user, ws_repo)

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, table_id=table_id)

    columns, col_ids = _build_columns(_PM_COLUMNS)
    view_repo = TableViewRepository(session)
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    for col in columns:
        try:
            await table_repo.create_column_index(table.table_id, col["column_id"], col["type"])
        except Exception:
            pass

    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Sprint Board",
        view_type="kanban",
        config={
            "group_by": col_ids.get("Status", ""),
            "card_fields": [col_ids.get("Title", ""), col_ids.get("Priority", ""), col_ids.get("Assignee", "")],
        },
        created_by=user.user_id,
    )
    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Roadmap",
        view_type="timeline",
        config={
            "start_col": col_ids.get("Start Date", ""),
            "end_col": col_ids.get("Due Date", ""),
            "color_by": col_ids.get("Status", ""),
            "group_by": col_ids.get("Type", ""),
        },
        created_by=user.user_id,
    )
    await view_repo.set_order(
        table.workspace_id,
        table.table_id,
        ["Sprint Board", "Roadmap"],
        updated_by=user.user_id,
    )

    return await _build_table_response(table, session)


# --------------------------------------------------
# CRM TEMPLATE
# --------------------------------------------------

_CRM_COLUMNS: list[dict[str, Any]] = [
    {"name": "Doc", "type": "doc"},
    {"name": "Title", "type": "text"},
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


@router.post("/template/crm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_crm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table_id = data.get("table_id", "") or data.get("table_name", "") or data.get("name", "")
    if not table_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="table_id is required")
    ws_repo = WorkspaceRepository(session)
    workspace_id = await _resolve_template_workspace(data, user, ws_repo)

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, table_id=table_id)

    columns, col_ids = _build_columns(_CRM_COLUMNS)
    view_repo = TableViewRepository(session)
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    for col in columns:
        try:
            await table_repo.create_column_index(table.table_id, col["column_id"], col["type"])
        except Exception:
            pass

    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Pipeline",
        view_type="kanban",
        config={
            "group_by": col_ids.get("Stage", ""),
            "card_fields": [col_ids.get("Title", ""), col_ids.get("Value", ""), col_ids.get("Owner", "")],
        },
        created_by=user.user_id,
    )
    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Sales Dashboard",
        view_type="dashboard",
        config={
            "layout": [
                {"id": "pipeline_value", "x": 0, "y": 0, "w": 3, "h": 2},
                {"id": "by_stage", "x": 3, "y": 0, "w": 6, "h": 4},
                {"id": "by_owner", "x": 9, "y": 0, "w": 3, "h": 4},
                {"id": "won_value", "x": 0, "y": 2, "w": 3, "h": 2},
                {"id": "recent", "x": 0, "y": 4, "w": 12, "h": 4},
            ],
            "blocks": {
                "pipeline_value": {
                    "kind": "number",
                    "title": "Pipeline Value",
                    "lql": (
                        f'table("{table_id}")'
                        ' | filter((r)->{r.stage in @["lead","qualified","proposal"]})'
                        ' | aggregate(@{"value": sum(r.value)})'
                    ),
                    "field": "value",
                    "format": "$,.0f",
                },
                "by_stage": {
                    "kind": "chart",
                    "title": "Value by Stage",
                    "lql": (
                        f'table("{table_id}") | group_by((r)->{{r.stage}}) | aggregate(@{{"value": sum(r.value)}})'
                    ),
                    "echarts": {
                        "dataset": [{"$inject": "rows"}],
                        "xAxis": {"type": "category"},
                        "yAxis": {"type": "value"},
                        "series": [{"type": "bar", "encode": {"x": "dim_0", "y": "value"}}],
                    },
                },
                "by_owner": {
                    "kind": "chart",
                    "title": "Deals by Owner",
                    "lql": f'table("{table_id}") | group_by((r)->{{r.owner}}) | aggregate(count())',
                    "echarts": {
                        "dataset": [{"$inject": "rows"}],
                        "xAxis": {"type": "category"},
                        "yAxis": {"type": "value"},
                        "series": [{"type": "bar", "encode": {"x": "dim_0", "y": "count"}}],
                    },
                },
                "won_value": {
                    "kind": "number",
                    "title": "Won Value",
                    "lql": (
                        f'table("{table_id}") | filter((r)->{{r.stage=="won"}}) | aggregate(@{{"value": sum(r.value)}})'
                    ),
                    "field": "value",
                    "format": "$,.0f",
                },
                "recent": {
                    "kind": "list",
                    "title": "Recent Deals",
                    "lql": f'table("{table_id}") | limit(10)',
                    "columns": [],
                },
            },
        },
        created_by=user.user_id,
    )
    await view_repo.set_order(
        table.workspace_id,
        table.table_id,
        ["Pipeline", "Sales Dashboard"],
        updated_by=user.user_id,
    )

    return await _build_table_response(table, session)


# Keep imports referenced even if a section is unused — keeps refactor safe.
_ = SCHEMA_ROW_NAME, ORDER_ROW_NAME
