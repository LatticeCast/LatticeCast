"""Immutable blob publication and durable, multi-worker-safe garbage collection."""

import asyncio

from sqlalchemy import text

from config.settings import settings
from config.storage import s3_client
from core import db as core_db
from core.db import get_login_session
from util import logger


async def queue_orphan_upload(key: str) -> None:
    """Queue an uploaded object when its row transaction could not publish it.

    The manager queue accepts keys even after the owning row/workspace was
    deleted. Cleanup checks for a live reference, so ambiguous commits are
    safe to queue as well.
    """
    async for session in get_login_session():
        await session.execute(
            text("""
                INSERT INTO private.blob_cleanup_queue (object_key)
                VALUES (:key) ON CONFLICT (object_key) DO NOTHING
            """),
            {"key": key},
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


# Reserved session advisory lock for the single blob cleanup leader.
CLEANUP_LEADER_LOCK_KEY = 0x4C435F424C4F42


async def cleanup_loop() -> None:
    # Only the elected worker drains the queue; retry if its connection is lost.
    while True:
        try:
            if core_db.login_engine is None:
                raise RuntimeError("Login database engine is not initialized")
            async with core_db.login_engine.connect() as leader:
                acquired = (
                    await leader.execute(
                        text("SELECT pg_try_advisory_lock(:key)"),
                        {"key": CLEANUP_LEADER_LOCK_KEY},
                    )
                ).scalar_one()
                await leader.commit()
                if not acquired:
                    await asyncio.sleep(5)
                    continue
                try:
                    while True:
                        # Detect a lost leader connection before starting work.
                        await leader.execute(text("SELECT 1"))
                        await leader.commit()
                        try:
                            await cleanup_once()
                        except Exception as exc:
                            logger.warn(f"Blob cleanup worker will retry: {exc}")
                        await asyncio.sleep(5)
                finally:
                    try:
                        await leader.execute(
                            text("SELECT pg_advisory_unlock(:key)"),
                            {"key": CLEANUP_LEADER_LOCK_KEY},
                        )
                        await leader.commit()
                    except Exception as exc:
                        logger.warn(f"Blob cleanup leader unlock failed: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warn(f"Blob cleanup leader will retry: {exc}")
            await asyncio.sleep(5)
