# src/middleware/jwks.py
"""
JWKS fetching and caching for OAuth providers.
"""

import time

import httpx
from fastapi import HTTPException

from config.pg_cache import cache_get, cache_set
from config.settings import settings
from util import logger

AUTHENTIK_JWKS_CACHE_KEY = "authentik:jwks"
GOOGLE_JWKS_CACHE_KEY = "google:jwks"
JWKS_CACHE_TTL = 3600


async def get_jwks(provider: str = "authentik") -> dict:
    """Fetch JWKS from the PG cache or provider"""
    start = time.time()
    cache_key = GOOGLE_JWKS_CACHE_KEY if provider == "google" else AUTHENTIK_JWKS_CACHE_KEY

    # Try cache first
    cache_start = time.time()
    try:
        cached = await cache_get(cache_key)
        logger.debug(f"Cache GET ({provider}): {time.time() - cache_start:.3f}s")
        if cached:
            logger.debug(f"JWKS from cache ({provider}, total: {time.time() - start:.3f}s)")
            return cached
    except Exception as e:
        logger.warn(f"Cache error: {e}")

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

                    # Cache it
                    cache_write_start = time.time()
                    try:
                        await cache_set(cache_key, jwks, JWKS_CACHE_TTL)
                        logger.debug(f"Cache SET: {time.time() - cache_write_start:.3f}s")
                        logger.info(f"JWKS fetched and cached ({provider}, total: {time.time() - start:.3f}s)")
                    except Exception as e:
                        logger.warn(f"Cache write failed: {e}")

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
