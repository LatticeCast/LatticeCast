# src/config/redis.py
# Uses redis-py library (wire-compatible with Valkey)
import redis.asyncio as redis

from config.settings import settings

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get Valkey client singleton (via redis-py)"""
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(
            settings.redis.url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            socket_timeout=settings.redis.socket_timeout,
        )
    return redis_client


async def close_redis():
    """Close Valkey connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
