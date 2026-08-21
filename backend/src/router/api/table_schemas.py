from fastapi import APIRouter, Depends
from sqlalchemy import text

from middleware.auth import get_current_user, get_rls_session
from repository.workspace import WorkspaceRepository

router = APIRouter(prefix="/sidebar")


@router.get("")
async def get_user_sidebar(user=Depends(get_current_user), session=Depends(get_rls_session)):
    r = await session.execute(text("SELECT public.get_user_sidebar()"))
    payload = r.scalar_one()
    repo = WorkspaceRepository(session)
    for workspace in payload.get("workspaces", []):
        workspace["level"] = await repo.get_user_level(workspace["workspace_id"], user.user_id)
    return payload
