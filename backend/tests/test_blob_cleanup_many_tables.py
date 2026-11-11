"""Cleanup stays table-targeted after a workspace grows beyond 64 tables."""

import asyncio
from time import time_ns
from unittest.mock import patch

import httpx
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from core.db import apply_rls_identity, close_db, get_login_session, init_db
from main import app
from middleware.auth import get_current_user
from models.user import User
from router.api import rows
from services import blob_objects


class MemoryStorage:
    def __init__(self):
        self.uploaded = set()
        self.deleted = set()
        self.relation_locks = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def put_object(self, **kwargs):
        self.uploaded.add(kwargs["Key"])

    async def delete_object(self, **kwargs):
        # Inspect the actual cleanup transaction while it is waiting on
        # storage. The old public.rows scan held over 10,000 relation locks.
        async for session in get_login_session():
            locks = await session.execute(
                text("""
                    SELECT count(*) FROM pg_locks
                    WHERE locktype = 'relation' AND pid = (
                        SELECT pid FROM pg_stat_activity
                        WHERE application_name = 'lc_blob_cleanup'
                        AND state = 'idle in transaction'
                        LIMIT 1
                    )
                """)
            )
            self.relation_locks.append(locks.scalar_one())
        self.deleted.add(kwargs["Key"])


def test_cleanup_across_more_than_64_tables():
    async def probe():
        had_identity_hook = event.contains(Session, "after_begin", apply_rls_identity)
        await init_db()
        async for session in get_login_session():
            user_id = (
                await session.execute(text("SELECT user_id FROM gdpr.user_info WHERE user_name = 'lattice'"))
            ).scalar_one()
        app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id, role="admin")
        storage = MemoryStorage()
        transport = httpx.ASGITransport(app=app)
        workspace_id = None
        try:
            with (
                patch.object(rows, "s3_client", return_value=storage),
                patch.object(blob_objects, "s3_client", return_value=storage),
            ):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post(
                        "/api/v1/workspaces", json={"workspace_name": f"cleanup-many-{time_ns()}"}
                    )
                    assert created.status_code == 201, created.text
                    workspace_id = created.json()["workspace_id"]
                    retired = set()
                    live_key = None
                    for number in range(65):
                        table = await client.post(
                            "/api/v1/tables",
                            json={"workspace_id": workspace_id, "table_name": f"articles-{number}"},
                        )
                        assert table.status_code == 201, table.text
                        table_data = table.json()
                        table_id = table_data["table_id"]
                        column_id = next(c["column_id"] for c in table_data["columns"] if c["name"] == "Doc")
                        row = await client.post(f"/api/v1/tables/{table_id}/rows", json={"row_data": {}})
                        assert row.status_code == 201, row.text
                        path = f"/api/v1/tables/{table_id}/rows/{row.json()['row_id']}/blob/{column_id}"
                        uploaded = await client.put(path, files={"file": ("doc.txt", b"data")})
                        assert uploaded.status_code == 200, uploaded.text
                        key = uploaded.json()["key"]
                        if number < 64:
                            removed = await client.delete(path)
                            assert removed.status_code == 204, removed.text
                            retired.add(key)
                        else:
                            live_key = key

                    # Every key is queued on registration. Retired keys need
                    # storage deletion; the still-referenced key must survive.
                    remaining_count = None
                    for _ in range(80):
                        await blob_objects.cleanup_once()
                        async for session in get_login_session():
                            remaining = await session.execute(
                                text("SELECT count(*) FROM private.blob_cleanup_queue WHERE object_key = ANY(:keys)"),
                                {"keys": list(retired | {live_key})},
                            )
                            remaining_count = remaining.scalar_one()
                        if remaining_count == 0:
                            break
                    assert storage.deleted & retired == retired
                    assert len(storage.relation_locks) == 64
                    assert max(storage.relation_locks) < 64
                    assert live_key in storage.uploaded
                    assert live_key not in storage.deleted
                    assert remaining_count == 0
        finally:
            if workspace_id is not None:
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    await client.delete(f"/api/v1/workspaces/{workspace_id}")
            app.dependency_overrides.pop(get_current_user, None)
            await close_db()
            if not had_identity_hook:
                event.remove(Session, "after_begin", apply_rls_identity)

    asyncio.run(probe())
