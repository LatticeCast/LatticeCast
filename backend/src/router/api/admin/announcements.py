"""Admin access to the fixed announcement workspace."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session
from middleware.auth import get_rls_session, require_admin
from models.user import User
from repository.row import RowRepository
from repository.table_view import TableViewRepository

ANNOUNCEMENT_WORKSPACE_ID = "f8bb8500-10f2-4e8c-b0a3-0d5c30778086"
ANNOUNCEMENT_TABLE_ID = "announcement"

router = APIRouter(prefix="/admin/announcements", tags=["admin-announcements"])


class AnnouncementCreateRequest(BaseModel):
    type: Literal["server", "app"]
    title: str
    description: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_announcement(
    body: AnnouncementCreateRequest,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_rls_session),
    login: AsyncSession = Depends(get_login_session),
) -> dict[str, int]:
    """Create one announcement row in the fixed lattice-cast announcement table.

    The caller's grant on the announcement workspace is materialized first.
    Without it RLS hides the table from this session entirely, so the schema
    read below comes back empty and every required column reads as missing --
    which is how a freshly migrated database behaved, since nothing else ever
    performs the grant. grant_announcement_admin is idempotent, re-checks
    role = 'admin' itself, and cannot target another workspace; it needs the
    mgr engine because only mgr holds EXECUTE on it (V37).
    """
    await login.execute(
        text("SELECT public.grant_announcement_admin(CAST(:user_id AS uuid))").bindparams(user_id=str(user.user_id))
    )
    await login.commit()

    schema = await TableViewRepository(session).get_tables_schema(ANNOUNCEMENT_WORKSPACE_ID, ANNOUNCEMENT_TABLE_ID)
    columns = {column["name"]: column["column_id"] for column in schema.get("columns", [])}
    required = ("Type", "Title", "Description", "updated_at", "updated_by", "created_at", "created_by")
    missing = [name for name in required if name not in columns]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Announcement table missing columns: {', '.join(sorted(set(missing)))}",
        )

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    row_data = {
        columns["Type"]: body.type,
        columns["Title"]: body.title,
        columns["Description"]: body.description,
        columns["updated_at"]: now_ms,
        columns["updated_by"]: str(user.user_id),
        columns["created_at"]: now_ms,
        columns["created_by"]: str(user.user_id),
    }

    row = await RowRepository(session).create(
        workspace_id=ANNOUNCEMENT_WORKSPACE_ID,
        table_id=ANNOUNCEMENT_TABLE_ID,
        row_data=row_data,
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    return {"row_id": row.row_id}
