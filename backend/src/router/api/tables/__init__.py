from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table import TableCreate, TableResponse
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

from ._shared import _build_table_response
from .columns import router as columns_router
from .crud import router as crud_router
from .templates import router as templates_router
from .views import router as views_router

router = APIRouter(prefix="/tables", tags=["tables"])


# Root-level routes (path "") must live on a router with a non-empty prefix —
# crud.py / templates.py / views.py / columns.py all have empty prefix so they
# can't host an empty path. POST + GET list live here for that reason.


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
        {"column_id": str(uuid4()), "name": "Title", "type": "text", "options": {}, "position": 0},
        {"column_id": str(uuid4()), "name": "Doc", "type": "doc", "options": {}, "position": 1},
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


router.include_router(templates_router)
router.include_router(crud_router)
router.include_router(columns_router)
router.include_router(views_router)
