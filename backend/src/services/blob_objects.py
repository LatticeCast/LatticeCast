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
    """Process each queued key in its own transaction without reading rows."""
    processed = 0
    async for session in get_login_session():
        result = await session.execute(
            text("""
                SELECT queue.object_key
                FROM private.blob_cleanup_queue AS queue
                LEFT JOIN private.blob_objects AS owned
                    ON owned.object_key = queue.object_key
                WHERE owned.object_key IS NULL OR owned.is_referenced IS NOT NULL
                ORDER BY queue.queued_at LIMIT 16
            """)
        )
        keys = list(result.scalars())
        await session.commit()
        for key in keys:
            try:
                await session.execute(text("SELECT set_config('application_name', 'lc_blob_cleanup', true)"))
                claimed = await session.execute(
                    text("""
                        SELECT 1 FROM private.blob_cleanup_queue
                        WHERE object_key = :key FOR UPDATE SKIP LOCKED
                    """),
                    {"key": key},
                )
                if claimed.scalar_one_or_none() is None:
                    await session.rollback()
                    continue
                locked = await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
                )
                if not locked.scalar_one():
                    await session.rollback()
                    continue

                # The row trigger maintains reference state in private storage.
                # Never open public.rows here: its many table-scoped indexes
                # consume relation locks even for a primary-key lookup.
                owner = await session.execute(
                    text("""
                        SELECT is_referenced
                        FROM private.blob_objects WHERE object_key = :key
                    """),
                    {"key": key},
                )
                address = owner.one_or_none()
                if address is not None and address.is_referenced is None:
                    # A pre-migration ownership record is not yet classified.
                    # Retain its bytes until a row mutation resolves it.
                    await session.rollback()
                    continue
                referenced = address is not None and address.is_referenced

                if not referenced:
                    async with s3_client() as s3:
                        await s3.delete_object(Bucket=settings.blob.bucket, Key=key)
                    await session.execute(
                        text("DELETE FROM private.blob_objects WHERE object_key = :key"), {"key": key}
                    )
                await session.execute(
                    text("DELETE FROM private.blob_cleanup_queue WHERE object_key = :key"), {"key": key}
                )
                await session.commit()
                processed += 1
            except Exception as exc:
                await session.rollback()
                logger.warn(f"Blob cleanup will retry {key}: {exc}")
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
