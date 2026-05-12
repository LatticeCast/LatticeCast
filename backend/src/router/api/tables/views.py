from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table_view import RESERVED_NAMES, SCHEMA_VIEW_DISPLAY_NAME, USER_VIEW_TYPES
from models.user import User
from models.view import ViewCreate, validate_view_config
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(tags=["tables"])


def _view_to_dict(view: Any) -> dict[str, Any]:
    return {
        "name": view.name,
        "type": view.type,
        "config": view.config,
    }


def _ensure_user_view_name(name: str) -> None:
    if name in RESERVED_NAMES or name.lower() == SCHEMA_VIEW_DISPLAY_NAME.lower():
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
# VIEW ORDER
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
# DEFAULT VIEW
# --------------------------------------------------


class DefaultViewRequest(BaseModel):
    name: str


@router.put("/{table_id}/default-view")
async def put_default_view(
    table_id: str,
    data: DefaultViewRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, str | None]:
    """Mark `data.name` as the table's default view. Refuses internal rows
    (__schema__/__order__) at the SQL function level."""
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    try:
        await view_repo.set_default_view(table.workspace_id, table.table_id, data.name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"default_view": data.name}
