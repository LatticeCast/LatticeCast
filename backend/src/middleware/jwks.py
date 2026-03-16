# src/middleware/jwks.py
"""
JWKS fetching and caching for OAuth providers.
"""

import json
import time

import httpx
from fastapi import HTTPException

from config.redis import get_redis
from config.settings import settings
from util import logger

AUTHENTIK_JWKS_CACHE_KEY = "authentik:jwks"
GOOGLE_JWKS_CACHE_KEY = "google:jwks"
JWKS_CACHE_TTL = 3600


async def get_jwks(provider: str = "authentik") -> dict:
    """Fetch JWKS from Valkey cache or provider"""
    start = time.time()
    redis = await get_redis()
    logger.debug(f"Valkey connection: {time.time() - start:.3f}s")

    cache_key = GOOGLE_JWKS_CACHE_KEY if provider == "google" else AUTHENTIK_JWKS_CACHE_KEY

    # Try cache first
    cache_start = time.time()
    try:
        cached = await redis.get(cache_key)
        logger.debug(f"Valkey GET ({provider}): {time.time() - cache_start:.3f}s")
        if cached:
            logger.debug(f"JWKS from cache ({provider}, total: {time.time() - start:.3f}s)")
            return json.loads(cached)
    except Exception as e:
        logger.warn(f"Valkey error: {e}")

    # Fetch from provider
    logger.info(f"Fetching JWKS from {provider}...")

    if provider == "google":
        jwks_urls = [settings.google.jwks_url]
    else:
        jwks_urls = [
            settings.authentik.jwks_url,
            f"{settings.authentik.url}/application/o/jwks/",
        ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in jwks_urls:
            try:
                url_start = time.time()
                resp = await client.get(url)
                logger.debug(f"HTTP GET {url}: {time.time() - url_start:.3f}s (status: {resp.status_code})")

                if resp.status_code == 200:
                    jwks = resp.json()

                    # Cache in Valkey
                    cache_write_start = time.time()
                    try:
                        await redis.setex(cache_key, JWKS_CACHE_TTL, json.dumps(jwks))
                        logger.debug(f"Valkey SET: {time.time() - cache_write_start:.3f}s")
                        logger.info(f"JWKS fetched and cached ({provider}, total: {time.time() - start:.3f}s)")
                    except Exception as e:
                        logger.warn(f"Valkey cache write failed: {e}")

                    return jwks
            except httpx.TimeoutException:
                logger.warn(f"TIMEOUT for {url}")
            except Exception as e:
                logger.warn(f"Failed {url}: {e}")
                continue

    raise HTTPException(
        status_code=503,
        detail=f"{provider} JWKS unreachable",
    )
