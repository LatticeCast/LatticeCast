from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table_view import USER_VIEW_TYPES
from models.user import User
from models.view import validate_view_config
from repository.table_view import TableViewRepository

from ._shared import _get_table_for_member

router = APIRouter(prefix="/tables", tags=["tables"])


def _view_dict(view: Any) -> dict[str, Any]:
    return {
        "view_id": view.view_id,
        "name": view.name,
        "type": view.type,
        "config": view.config,
    }


def _ensure_user_view_type(view_type: str) -> None:
    if view_type not in USER_VIEW_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"View type must be one of {USER_VIEW_TYPES}",
        )


# ── Reads ────────────────────────────────────────────────────────────────


@router.get("/{table_id}/views")
async def list_views(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> list[dict[str, Any]]:
    """All user views for a table, ordered per table_schemas.view_order."""
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    schema = await view_repo.get_tables_schema(table.workspace_id, table.table_id)
    return list(schema.get("views", []))


@router.get("/{table_id}/views/{view_id}")
async def get_view(
    table_id: str,
    view_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view = await TableViewRepository(session).get_by_id(
        table.workspace_id, table.table_id, view_id
    )
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    return _view_dict(view)


# ── Mutations (return full schema) ──────────────────────────────────────


@router.post("/{table_id}/views", status_code=status.HTTP_201_CREATED)
async def create_view(
    table_id: str,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Body: {name, type, config?}. Name + type are merged into the
    config blob before being passed to the V14 create_view PG function."""
    table = await _get_table_for_member(table_id, user, session)
    name = (data.get("name") or "").strip()
    view_type = data.get("type") or ""
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="View name is required")
    _ensure_user_view_type(view_type)
    extra_config = data.get("config") or {}
    try:
        validate_view_config(view_type, extra_config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    full_config = {"name": name, "type": view_type, **extra_config}
    view_repo = TableViewRepository(session)
    return await view_repo.create_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        config=full_config,
        created_by=user.user_id,
    )


@router.put("/{table_id}/views/{view_id}")
async def update_view(
    table_id: str,
    view_id: int,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Body: any subset of {name, type, config}. The PG function merges
    these into the row's config JSONB."""
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_id(table.workspace_id, table.table_id, view_id)
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")

    patch: dict[str, Any] = {}
    if "name" in data:
        patch["name"] = data["name"]
    if "type" in data:
        _ensure_user_view_type(data["type"])
        patch["type"] = data["type"]
    if "config" in data:
        patch.update(data["config"] or {})

    return await view_repo.update_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        view_id=view_id,
        patch=patch,
        updated_by=user.user_id,
    )


@router.delete("/{table_id}/views/{view_id}")
async def delete_view(
    table_id: str,
    view_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_id(table.workspace_id, table.table_id, view_id)
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    return await view_repo.delete_view(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        view_id=view_id,
        deleted_by=user.user_id,
    )


# view-order / default-view are sub-fields of PATCH /tables/{tid}/schema
# in crud.py — see _shared.py / crud.py.
