from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table import TableResponse, TableUpdate
from models.user import User
from repository.table import TableRepository

from ._shared import _build_table_response, _get_table_for_member

# Root-level routes (POST/GET on /tables) live in __init__.py — they need the
# parent router's non-empty prefix to register with an empty route path.
# Per-id routes (get/put/delete /{table_id}) stay here.
router = APIRouter(tags=["tables"])


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
