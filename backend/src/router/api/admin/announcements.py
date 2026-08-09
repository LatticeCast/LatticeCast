"""Admin access to the fixed announcement workspace."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session
from middleware.auth import require_admin
from models.user import User

router = APIRouter(prefix="/admin/announcements", tags=["admin-announcements"])


@router.post("/join", status_code=status.HTTP_204_NO_CONTENT)
async def join_announcement_workspace(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_login_session),
) -> None:
    """Give an admin caller owner access to the fixed announcement workspace."""
    await session.execute(
        text("SELECT public.grant_announcement_admin(CAST(:user_id AS uuid))").bindparams(user_id=str(user.user_id))
    )
    await session.commit()
