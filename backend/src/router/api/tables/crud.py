"""CRUD on the tables collection + per-table identity + schema PATCH.

- POST  /tables                       — create blank table
- GET   /tables                       — list all tables across user's workspaces
- GET   /tables/{table_id}            — single table (full schema snapshot)
- PUT   /tables/{table_id}            — rename table_id
- DELETE /tables/{table_id}           — drop table
- PATCH /tables/{table_id}/schema     — update {view_order, default_view, col_order};
                                        returns the new full TableSchema
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import invalidate_schema_cache
from middleware.auth import get_current_user, get_rls_session
from models.table import TableCreate, TableResponse, TableUpdate
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

from ._shared import _build_table_response, _get_table_for_member

router = APIRouter(prefix="/tables", tags=["tables"])


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Create a blank table via the V38 PG function — atomic INSERT +
    __schema__/__order__ setup + per-column indexes in one transaction."""
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
    table = await table_repo.create_from_template(
        workspace_id=workspace_id,
        table_id=data.table_id,
        kind="blank",
        created_by=user.user_id,
    )
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
    workspace_id: UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Read a table's full schema. `workspace_id` query param disambiguates
    when the user belongs to multiple workspaces that each have a table
    with this `table_id` (the URL `/{ws}/{tid}` collision case)."""
    table = await _get_table_for_member(table_id, user, session, workspace_id=workspace_id)
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


# ── PATCH /tables/{table_id}/schema ────────────────────────────────────
# One endpoint covers FE drag-reorder-views, click-set-default-view, and
# drag-reorder-columns. Body is a partial — any subset of the three keys.
# Returns the new full TableSchema so the FE replaces its local cache
# from the response.


class SchemaPatch(BaseModel):
    view_order: list[int] | None = None
    default_view: int | None = None
    col_order: list[str] | None = None


@router.patch("/{table_id}/schema")
async def patch_schema(
    table_id: str,
    data: SchemaPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    table = await _get_table_for_member(table_id, user, session)
    view_repo = TableViewRepository(session)

    if data.view_order is not None:
        await view_repo.set_order(
            table.workspace_id, table.table_id, data.view_order, updated_by=user.user_id
        )
    if data.col_order is not None:
        await view_repo.update_col_order(
            table.workspace_id, table.table_id, data.col_order, updated_by=user.user_id
        )
        await invalidate_schema_cache(str(table.workspace_id))
    if data.default_view is not None:
        try:
            await view_repo.set_default_view(
                table.workspace_id, table.table_id, data.default_view, updated_by=user.user_id
            )
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return await view_repo.get_tables_schema(table.workspace_id, table.table_id)
