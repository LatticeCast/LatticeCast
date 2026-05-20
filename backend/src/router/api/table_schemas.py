from fastapi import APIRouter, Depends
from sqlalchemy import text

from middleware.auth import get_current_user, get_rls_session

router = APIRouter(prefix="/sidebar")


@router.get("")
async def get_user_sidebar(user=Depends(get_current_user), session=Depends(get_rls_session)):
    r = await session.execute(text("SELECT public.get_user_sidebar(CAST(:u AS UUID))"), {"u": str(user.user_id)})
    return r.scalar_one()
