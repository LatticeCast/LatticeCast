from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table import TableResponse
from models.user import User
from repository.table import TableRepository
from repository.workspace import WorkspaceRepository

from ._shared import _build_table_response

router = APIRouter(prefix="/tables", tags=["tables"])


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


async def _create_from_template(
    kind: str,
    data: dict[str, Any],
    user: User,
    session: AsyncSession,
) -> dict[str, Any]:
    table_id = data.get("table_id", "") or data.get("table_name", "") or data.get("name", "")
    if not table_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="table_id is required")
    ws_repo = WorkspaceRepository(session)
    workspace_id = await _resolve_template_workspace(data, user, ws_repo)
    table_repo = TableRepository(session)
    table = await table_repo.create_from_template(
        workspace_id=workspace_id,
        table_id=table_id,
        kind=kind,
        created_by=user.user_id,
    )
    return await _build_table_response(table, session)


@router.post("/template/pm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_pm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """V38: one PG function call replaces the multi-step orchestration —
    columns, indexes, Sprint Board + Roadmap views, default-view flag, all
    in one transaction."""
    return await _create_from_template("pm", data, user, session)


@router.post("/template/crm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_crm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """V38: one PG function call replaces the multi-step orchestration —
    columns, indexes, Pipeline + Sales Dashboard views, default-view flag,
    all in one transaction."""
    return await _create_from_template("crm", data, user, session)
