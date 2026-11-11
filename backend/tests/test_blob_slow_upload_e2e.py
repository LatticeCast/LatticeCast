"""API and PostgreSQL regression: slow S3 must not pin row/table locks."""

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


class SlowStorage:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.slow_key = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def put_object(self, **kwargs):
        if kwargs["Body"] == b"slow-upload":
            self.slow_key = kwargs["Key"]
            self.started.set()
            await self.release.wait()


def test_slow_blob_upload_allows_other_put_and_workspace_delete():
    async def probe():
        had_identity_hook = event.contains(Session, "after_begin", apply_rls_identity)
        await init_db()
        async for session in get_login_session():
            user_id = (
                await session.execute(text("SELECT user_id FROM gdpr.user_info WHERE user_name = 'lattice'"))
            ).scalar_one()
        app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id, role="admin")
        storage = SlowStorage()
        transport = httpx.ASGITransport(app=app)
        workspace_id = None
        try:
            with patch.object(rows, "s3_client", return_value=storage):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post("/api/v1/workspaces", json={"workspace_name": f"slow-blob-{time_ns()}"})
                    assert created.status_code == 201, created.text
                    workspace_id = created.json()["workspace_id"]
                    table_response = await client.post(
                        "/api/v1/tables", json={"workspace_id": workspace_id, "table_name": "articles"}
                    )
                    assert table_response.status_code == 201, table_response.text
                    table = table_response.json()
                    table_id = table["table_id"]
                    column_id = next(c["column_id"] for c in table["columns"] if c["name"] == "Doc")
                    row_ids = []
                    for _ in range(2):
                        response = await client.post(f"/api/v1/tables/{table_id}/rows", json={"row_data": {}})
                        assert response.status_code == 201, response.text
                        row_ids.append(response.json()["row_id"])

                    slow_path = f"/api/v1/tables/{table_id}/rows/{row_ids[0]}/blob/{column_id}"
                    fast_path = f"/api/v1/tables/{table_id}/rows/{row_ids[1]}/blob/{column_id}"
                    slow = asyncio.create_task(client.put(slow_path, files={"file": ("slow.txt", b"slow-upload")}))
                    try:
                        await asyncio.wait_for(storage.started.wait(), timeout=5)
                        fast = await asyncio.wait_for(
                            client.put(fast_path, files={"file": ("fast.txt", b"fast-upload")}),
                            timeout=5,
                        )
                        assert fast.status_code == 200, fast.text
                        deleted = await asyncio.wait_for(client.delete(f"/api/v1/workspaces/{workspace_id}"), timeout=5)
                        assert deleted.status_code == 204, deleted.text
                        workspace_id = None
                    finally:
                        storage.release.set()
                    lost = await asyncio.wait_for(slow, timeout=5)
                    assert lost.status_code in (403, 404), lost.text
                    async for session in get_login_session():
                        queued = await session.execute(
                            text("SELECT 1 FROM private.blob_cleanup_queue WHERE object_key = :key"),
                            {"key": storage.slow_key},
                        )
                        assert queued.scalar_one_or_none() == 1
        finally:
            if workspace_id is not None:
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    await client.delete(f"/api/v1/workspaces/{workspace_id}")
            app.dependency_overrides.pop(get_current_user, None)
            await close_db()
            if not had_identity_hook:
                event.remove(Session, "after_begin", apply_rls_identity)

    asyncio.run(probe())
