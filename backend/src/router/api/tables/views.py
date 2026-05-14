from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table_view import SCHEMA_VIEW_DISPLAY_NAME, USER_VIEW_TYPES
from models.user import User
from models.view import ViewCreate, validate_view_config
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(prefix="/tables", tags=["tables"])


def _view_to_dict(view: Any) -> dict[str, Any]:
    return {
        "name": view.name,
        "type": view.type,
        "config": view.config,
    }


def _ensure_user_view_name(name: str) -> None:
    # V44 CHECK constraint also enforces this at the DB; FE-friendly 400
    # spares the round-trip on obvious reserved names.
    if name.lower() == SCHEMA_VIEW_DISPLAY_NAME.lower() or name in (
        "__schema__",
        "__order__",
    ):
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
    """List user views for a table, ordered per table_schemas.view_order."""
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
    """V47: one PG call inserts the row AND appends to view_order
    atomically. Returns full table_schemas.config."""
    table = await _get_table_for_member(table_id, user, session)
    if not data.name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="View name is required")
    _ensure_user_view_name(data.name)
    _ensure_user_view_type(data.type)
    view_repo = TableViewRepository(session)
    if await view_repo.get_by_name(table.workspace_id, table.table_id, data.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
    try:
        validate_view_config(data.type, data.config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await view_repo.create_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name=data.name,
        view_type=data.type,
        config=data.config,
        created_by=user.user_id,
    )
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)


@router.put("/{table_id}/views/{view_name}")
async def update_view(
    table_id: str,
    view_name: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """V47: one PG call updates the row AND keeps view_order +
    default_view consistent on rename. Returns full schema config."""
    _ensure_user_view_name(view_name)
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_name(table.workspace_id, table.table_id, view_name)
    if not view or view.type not in USER_VIEW_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")

    patch: dict[str, Any] = {}
    if "name" in data and data["name"] != view.name:
        new_name = data["name"]
        _ensure_user_view_name(new_name)
        if await view_repo.get_by_name(table.workspace_id, table.table_id, new_name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="View name already exists")
        patch["name"] = new_name
    if "type" in data:
        _ensure_user_view_type(data["type"])
        patch["type"] = data["type"]
    if "config" in data:
        patch["config"] = data["config"]

    await view_repo.update_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        old_name=view_name,
        patch=patch,
        updated_by=user.user_id,
    )
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)


@router.delete("/{table_id}/views/{view_name}")
async def delete_view(
    table_id: str,
    view_name: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """V47: one PG call deletes the row, strips view_order, clears
    default_view if it pointed here. Returns full schema config."""
    _ensure_user_view_name(view_name)
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_name(table.workspace_id, table.table_id, view_name)
    if not view or view.type not in USER_VIEW_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    await view_repo.delete_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name=view_name,
        deleted_by=user.user_id,
    )
    return await view_repo.get_full_schema(table.workspace_id, table.table_id)


# view-order / default-view are now sub-fields of PATCH /tables/{tid}/schema
# in crud.py — see _shared.py / crud.py.
