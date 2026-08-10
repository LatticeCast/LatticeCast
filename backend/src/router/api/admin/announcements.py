"""Admin access to the fixed announcement workspace."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
) -> dict[str, int]:
    """Create one announcement row in the fixed lattice-cast announcement table.

    Caller must already hold write/owner on the announcement workspace via PG setup.
    """
    schema = await TableViewRepository(session).get_tables_schema(ANNOUNCEMENT_WORKSPACE_ID, ANNOUNCEMENT_TABLE_ID)
    columns = {column["name"]: column["column_id"] for column in schema.get("columns", [])}
    required = ("Type", "Title", "Description", "updated_at", "updated_by", "created_at", "created_by")
    missing = [name for name in required if name not in columns]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Announcement table missing columns: {', '.join(sorted(set(missing)))}",
        )

    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    row_data = {
        columns["Type"]: body.type,
        columns["Title"]: body.title,
        columns["Description"]: body.description,
        columns["updated_at"]: now_iso,
        columns["updated_by"]: str(user.user_id),
        columns["created_at"]: now_iso,
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
