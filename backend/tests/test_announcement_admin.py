"""Unit tests for the admin announcement create endpoint."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from models.user import User
from router.api.admin.announcements import (
    ANNOUNCEMENT_TABLE_ID,
    ANNOUNCEMENT_WORKSPACE_ID,
    AnnouncementCreateRequest,
    create_announcement,
)


def _run(coro) -> None:
    asyncio.run(coro)


class TestAnnouncementAdminCreate:
    def test_create_announcement_maps_named_columns_to_existing_table_schema(self):
        async def _run_test() -> None:
            admin = User(user_id=uuid4(), role="admin")
            session = AsyncMock()

            schema_repo = AsyncMock()
            schema_repo.get_tables_schema.return_value = {
                "columns": [
                    {"name": "Type", "column_id": "c-type"},
                    {"name": "Title", "column_id": "c-title"},
                    {"name": "Description", "column_id": "c-description"},
                    {"name": "updated_at", "column_id": "c-updated-at"},
                    {"name": "updated_by", "column_id": "c-updated-by"},
                    {"name": "created_at", "column_id": "c-created-at"},
                    {"name": "created_by", "column_id": "c-created-by"},
                ]
            }
            row_repo = AsyncMock()
            row_repo.create.return_value = SimpleNamespace(row_id=42)

            with (
                patch("router.api.admin.announcements.datetime") as mock_datetime,
                patch("router.api.admin.announcements.TableViewRepository", return_value=schema_repo),
                patch("router.api.admin.announcements.RowRepository", return_value=row_repo),
            ):
                mock_datetime.now.return_value = datetime(2026, 8, 10, 22, 0, 0, tzinfo=UTC)
                result = await create_announcement(
                    body=AnnouncementCreateRequest(
                        type="server",
                        title="Scheduled maintenance",
                        description="Deploy at 22:00",
                    ),
                    user=admin,
                    session=session,
                )

            schema_repo.get_tables_schema.assert_awaited_once_with(
                ANNOUNCEMENT_WORKSPACE_ID,
                ANNOUNCEMENT_TABLE_ID,
            )
            row_repo.create.assert_awaited_once_with(
                workspace_id=ANNOUNCEMENT_WORKSPACE_ID,
                table_id=ANNOUNCEMENT_TABLE_ID,
                row_data={
                    "c-type": "server",
                    "c-title": "Scheduled maintenance",
                    "c-description": "Deploy at 22:00",
                    "c-updated-at": "2026-08-10T22:00:00Z",
                    "c-updated-by": str(admin.user_id),
                    "c-created-at": "2026-08-10T22:00:00Z",
                    "c-created-by": str(admin.user_id),
                },
                created_by=admin.user_id,
                updated_by=admin.user_id,
            )
            assert result == {"row_id": 42}

        _run(_run_test())

    def test_create_announcement_rejects_schema_missing_required_columns(self):
        async def _run_test() -> None:
            admin = User(user_id=uuid4(), role="admin")
            session = AsyncMock()

            schema_repo = AsyncMock()
            schema_repo.get_tables_schema.return_value = {
                "columns": [
                    {"name": "Type", "column_id": "c-type"},
                    {"name": "Title", "column_id": "c-title"},
                ]
            }
            row_repo = AsyncMock()

            with (
                patch("router.api.admin.announcements.TableViewRepository", return_value=schema_repo),
                patch("router.api.admin.announcements.RowRepository", return_value=row_repo),
            ):
                try:
                    await create_announcement(
                        body=AnnouncementCreateRequest(
                            type="app",
                            title="Client release",
                            description="",
                        ),
                        user=admin,
                        session=session,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 500
                    assert (
                        exc.detail
                        == "Announcement table missing columns: Description, created_at, created_by, updated_at, updated_by"
                    )
                else:
                    raise AssertionError("Expected HTTPException")

            row_repo.create.assert_not_called()

        _run(_run_test())
