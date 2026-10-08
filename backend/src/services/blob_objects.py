"""Immutable blob publication and durable, multi-worker-safe garbage collection."""

import asyncio

from sqlalchemy import text

from config.settings import settings
from config.storage import s3_client
from core.db import get_login_session, get_session, set_rls_context
from util import logger


async def register_upload(table, row_id: int, column_id: str, key: str, user_id: str) -> None:
    """Commit the recovery record separately while the caller holds its lock.

    This record survives an interrupted upload or an ambiguous DB commit.
    The cleanup worker cannot touch the key until the publisher releases
    its PostgreSQL advisory transaction lock.
    """
    async for session in get_session():
        await set_rls_context(session, user_id)
        await session.execute(
            text("SELECT public.register_blob_object(:ws, :tid, :rid, :cid, :key)"),
            {"ws": str(table.workspace_id), "tid": table.table_id, "rid": row_id, "cid": column_id, "key": key},
        )
        await session.commit()


async def cleanup_once() -> int:
    """Process a small batch, retaining failed jobs for a later retry."""
    processed = 0
    async for session in get_login_session():
        result = await session.execute(
            text("""
                SELECT object_key FROM private.blob_cleanup_queue
                ORDER BY queued_at LIMIT 16 FOR UPDATE SKIP LOCKED
            """)
        )
        keys = list(result.scalars())
        for key in keys:
            locked = await session.execute(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
            )
            if not locked.scalar_one():
                continue
            referenced = await session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM public.rows AS r,
                        LATERAL jsonb_each(r.row_data) AS cell
                        WHERE cell.value ->> 'key' = :key
                    )
                """),
                {"key": key},
            )
            if not referenced.scalar_one():
                try:
                    async with s3_client() as s3:
                        await s3.delete_object(Bucket=settings.blob.bucket, Key=key)
                except Exception as exc:
                    logger.warn(f"Blob cleanup will retry: {exc}")
                    continue
                await session.execute(text("DELETE FROM private.blob_objects WHERE object_key = :key"), {"key": key})
            await session.execute(text("DELETE FROM private.blob_cleanup_queue WHERE object_key = :key"), {"key": key})
            processed += 1
        await session.commit()
    return processed


async def cleanup_loop() -> None:
    while True:
        try:
            await cleanup_once()
        except Exception as exc:
            logger.warn(f"Blob cleanup worker will retry: {exc}")
        await asyncio.sleep(5)
