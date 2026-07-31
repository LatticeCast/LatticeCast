# src/config/pg_cache.py
"""PostgreSQL-backed cache — replaces the former Valkey/Redis cache.

Backed by the UNLOGGED table private.cache (see migration
V31__pg_cache.sql), reached through three SECURITY DEFINER functions so
app_user never touches the private schema's table directly. UNLOGGED
tables skip WAL (fast writes, no replication) and are truncated on
crash — exactly the durability profile a cache needs.
"""

import json
from typing import Any

from sqlalchemy import text

from core import db as core_db


async def _get_session():
    if core_db.app_session_factory is None:
        await core_db.init_db()
    return core_db.app_session_factory()


async def cache_get(key: str) -> Any | None:
    """Return the cached JSON value for `key`, or None on miss/expiry."""
    async with await _get_session() as session:
        result = await session.execute(text("SELECT private.cache_get(:key)").bindparams(key=key))
        return result.scalar_one()


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Upsert `key` -> `value` (JSON-serializable) with a TTL in seconds."""
    async with await _get_session() as session:
        await session.execute(
            text("SELECT private.cache_set(:key, CAST(:val AS jsonb), :ttl)").bindparams(
                key=key, val=json.dumps(value), ttl=ttl_seconds
            )
        )
        await session.commit()


async def cache_delete(key: str) -> None:
    """Delete `key` from the cache."""
    async with await _get_session() as session:
        await session.execute(text("SELECT private.cache_delete(:key)").bindparams(key=key))
        await session.commit()
