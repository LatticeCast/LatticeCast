from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import compile_lql
from middleware.auth import get_current_user, get_rls_session
from models.user import User
from repository.dashboard import DashboardRepository
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(prefix="/tables", tags=["dashboard"])


class BlockQueryRequest(BaseModel):
    params: dict[str, Any] = {}


async def _get_table_for_member(table_id: str, user: User, session: AsyncSession):
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


@router.post("/{table_id}/views/{view_name}/blocks/{block_id}/query")
async def query_block(
    table_id: str,
    view_name: str,
    block_id: str,
    body: BlockQueryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Execute a dashboard block's LatticeQL query and return aggregated rows."""
    table = await _get_table_for_member(table_id, user, session)

    view_repo = TableViewRepository(session)
    view = await view_repo.get_by_name(table.workspace_id, table.table_id, view_name)
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    if view.type != "dashboard":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="View is not a dashboard")

    blocks = (view.config or {}).get("blocks", {})
    if block_id not in blocks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    lql = blocks[block_id].get("lql", "")
    try:
        sql, params = await compile_lql(lql, str(table.workspace_id), session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    rows = await DashboardRepository.execute(session, sql, params, body.params)
    return {"rows": rows}
