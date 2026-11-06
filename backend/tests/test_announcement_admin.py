"""Unit tests for the admin announcement create endpoint.

Rewritten for the current `create_announcement`: tables are addressed by a
DB-assigned numeric table_id resolved at request time (`TableRepository`),
not a fixed ANNOUNCEMENT_TABLE_ID constant, and the handler now also
materializes the caller's admin grant on a separate `login` (mgr) session
before touching the announcement workspace.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from models.user import User
from router.api.admin.announcements import (
    ANNOUNCEMENT_TABLE_NAME,
    ANNOUNCEMENT_WORKSPACE_ID,
    AnnouncementCreateRequest,
    create_announcement,
)


def _run(coro) -> None:
    asyncio.run(coro)


def _full_schema() -> dict:
    return {
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


class TestAnnouncementAdminCreate:
    def test_create_announcement_maps_named_columns_to_existing_table_schema(self):
        async def _run_test() -> None:
            admin = User(user_id=uuid4(), role="admin")
            session = AsyncMock()
            login = AsyncMock()

            table_repo = AsyncMock()
            table_repo.resolve_table_global.return_value = SimpleNamespace(table_id=7)
            schema_repo = AsyncMock()
            schema_repo.get_tables_schema.return_value = _full_schema()
            row_repo = AsyncMock()
            row_repo.create.return_value = SimpleNamespace(row_id=42)

            with (
                patch("router.api.admin.announcements.datetime") as mock_datetime,
                patch("router.api.admin.announcements.TableRepository", return_value=table_repo),
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
                    login=login,
                )

            # The caller's admin grant on the announcement workspace must be
            # materialized, on the mgr (login) session, before anything else.
            login.execute.assert_awaited_once()
            (grant_stmt,), _ = login.execute.call_args
            assert "grant_announcement_admin" in str(grant_stmt)
            login.commit.assert_awaited_once()

            table_repo.resolve_table_global.assert_awaited_once_with(
                ANNOUNCEMENT_TABLE_NAME, [UUID(ANNOUNCEMENT_WORKSPACE_ID)]
            )
            schema_repo.get_tables_schema.assert_awaited_once_with(ANNOUNCEMENT_WORKSPACE_ID, 7)
            row_repo.create.assert_awaited_once_with(
                workspace_id=ANNOUNCEMENT_WORKSPACE_ID,
                table_id=7,
                # date/datetime cells are epoch-millisecond numbers, not ISO strings.
                row_data={
                    "c-type": "server",
                    "c-title": "Scheduled maintenance",
                    "c-description": "Deploy at 22:00",
                    "c-updated-at": 1786399200000,
                    "c-updated-by": str(admin.user_id),
                    "c-created-at": 1786399200000,
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
            login = AsyncMock()

            table_repo = AsyncMock()
            table_repo.resolve_table_global.return_value = SimpleNamespace(table_id=7)
            schema_repo = AsyncMock()
            schema_repo.get_tables_schema.return_value = {
                "columns": [
                    {"name": "Type", "column_id": "c-type"},
                    {"name": "Title", "column_id": "c-title"},
                ]
            }
            row_repo = AsyncMock()

            with (
                patch("router.api.admin.announcements.TableRepository", return_value=table_repo),
                patch("router.api.admin.announcements.TableViewRepository", return_value=schema_repo),
                patch("router.api.admin.announcements.RowRepository", return_value=row_repo),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await create_announcement(
                        body=AnnouncementCreateRequest(
                            type="app",
                            title="Client release",
                            description="",
                        ),
                        user=admin,
                        session=session,
                        login=login,
                    )

            assert exc_info.value.status_code == 500
            assert (
                exc_info.value.detail
                == "Announcement table missing columns: Description, created_at, created_by, updated_at, updated_by"
            )
            row_repo.create.assert_not_called()

        _run(_run_test())

    def test_create_announcement_fails_closed_when_table_is_missing(self):
        """No resolvable announcement table -> 500, never a silent write."""

        async def _run_test() -> None:
            admin = User(user_id=uuid4(), role="admin")
            session = AsyncMock()
            login = AsyncMock()

            table_repo = AsyncMock()
            table_repo.resolve_table_global.return_value = None
            schema_repo = AsyncMock()
            row_repo = AsyncMock()

            with (
                patch("router.api.admin.announcements.TableRepository", return_value=table_repo),
                patch("router.api.admin.announcements.TableViewRepository", return_value=schema_repo),
                patch("router.api.admin.announcements.RowRepository", return_value=row_repo),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await create_announcement(
                        body=AnnouncementCreateRequest(type="app", title="x", description="y"),
                        user=admin,
                        session=session,
                        login=login,
                    )

            assert exc_info.value.status_code == 500
            schema_repo.get_tables_schema.assert_not_called()
            row_repo.create.assert_not_called()

        _run(_run_test())
