"""Unit tests for the admin announcement-workspace join endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from models.user import User
from router.api.admin.announcements import join_announcement_workspace


def _run(coro) -> None:
    asyncio.run(coro)


class TestAnnouncementAdminJoin:
    def test_join_grants_the_calling_admin_announcement_owner_access(self):
        """The grant function receives the authenticated admin's UUID."""

        async def _run_test() -> None:
            admin = User(user_id=uuid4(), role="admin")
            session = AsyncMock()
            session.execute = AsyncMock()
            session.commit = AsyncMock()

            await join_announcement_workspace(user=admin, session=session)

            session.execute.assert_awaited_once()
            statement = session.execute.call_args.args[0]
            assert statement.text == "SELECT public.grant_announcement_admin(CAST(:user_id AS uuid))"
            assert statement.compile().params == {"user_id": str(admin.user_id)}
            session.commit.assert_awaited_once()

        _run(_run_test())

    def test_join_keeps_announcement_access_changes_inside_the_grant_function(self):
        """The API service invokes a read-only SELECT, never direct membership DML."""

        async def _run_test() -> None:
            session = AsyncMock()
            session.execute = AsyncMock()
            session.commit = AsyncMock()

            await join_announcement_workspace(user=User(user_id=uuid4(), role="admin"), session=session)

            statement = session.execute.call_args.args[0]
            sql = statement.text.upper()
            assert sql.startswith("SELECT ")
            assert "WORKSPACE_MEMBERS" not in sql
            assert not any(keyword in sql for keyword in ("INSERT", "UPDATE", "DELETE"))

        _run(_run_test())
