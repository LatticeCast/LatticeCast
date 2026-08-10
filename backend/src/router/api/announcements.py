from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import compile_lql
from core.db import get_session
from repository.dashboard import DashboardRepository
from repository.table_view import TableViewRepository

ANNOUNCEMENT_USER_ID = "36baf5e2-b9ae-4ef6-9657-3445a323128c"
ANNOUNCEMENT_WORKSPACE_ID = "f8bb8500-10f2-4e8c-b0a3-0d5c30778086"

router = APIRouter(prefix="/announcements", tags=["announcements"])


class AnnouncementQueryRequest(BaseModel):
    lql: str


@router.post("/query")
async def query_announcements(
    body: AnnouncementQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run caller-provided LatticeQL against the read-only announcement data.

    This endpoint is intentionally public: callers do not need an app account.
    The backend always reads under the fixed announcement identity.
    """
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, false)").bindparams(uid=ANNOUNCEMENT_USER_ID)
    )
    schema = await TableViewRepository(session).get_tables_schema(ANNOUNCEMENT_WORKSPACE_ID, "announcement")
    try:
        sql, params = await compile_lql(body.lql, ANNOUNCEMENT_WORKSPACE_ID, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    rows = await DashboardRepository.execute(session, sql, params)
    return {
        "rows": rows,
        "columns": schema.get("columns", []) or [],
    }
