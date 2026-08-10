"""Focused tests for the public announcement query endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


def _run(coro):
    return asyncio.run(coro)


class TestAnnouncementQuery:
    def test_executes_caller_lql_as_read_only_announcement_user(self):
        """The endpoint compiles and executes supplied LQL under the announcement read identity."""

        async def _run_test():
            from router.api.announcements import (
                ANNOUNCEMENT_USER_ID,
                ANNOUNCEMENT_WORKSPACE_ID,
                AnnouncementQueryRequest,
                query_announcements,
            )

            session = AsyncMock()
            caller = object()
            caller_lql = 'table("Announcements") | limit(10)'
            compiled_sql = "SELECT title FROM rows"
            compiled_params: list[dict] = []
            expected_rows = [{"title": "Maintenance window"}]
            expected_schema = {"columns": [{"name": "Title", "column_id": "c-title"}], "views": []}

            with (
                patch(
                    "router.api.announcements.TableViewRepository",
                    return_value=AsyncMock(get_tables_schema=AsyncMock(return_value=expected_schema)),
                ) as schema_repo,
                patch(
                    "router.api.announcements.compile_lql",
                    new=AsyncMock(return_value=(compiled_sql, compiled_params)),
                ) as compile_lql,
                patch(
                    "router.api.announcements.DashboardRepository.execute",
                    new=AsyncMock(return_value=expected_rows),
                ) as execute,
            ):
                response = await query_announcements(AnnouncementQueryRequest(lql=caller_lql), caller, session)

            assert response == {"rows": expected_rows, "columns": expected_schema["columns"]}
            schema_repo.return_value.get_tables_schema.assert_awaited_once_with(
                ANNOUNCEMENT_WORKSPACE_ID,
                "announcement",
            )
            compile_lql.assert_awaited_once_with(caller_lql, ANNOUNCEMENT_WORKSPACE_ID, session)
            execute.assert_awaited_once_with(session, compiled_sql, compiled_params)

            session.execute.assert_awaited_once()
            access_statement = session.execute.await_args.args[0]
            assert "set_config('app.current_user_id'" in str(access_statement)
            assert access_statement.compile().params == {"uid": ANNOUNCEMENT_USER_ID}

        _run(_run_test())
