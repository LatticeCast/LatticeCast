# src/middleware/token.py
"""
Token verification for OAuth providers.
"""

import time

import httpx
from fastapi import Header, HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from config.settings import settings
from middleware.jwks import get_jwks
from services.lc_auth import LOCAL_ALGORITHM
from util import logger

ALGORITHM = "RS256"
def verify_local_token(token: str) -> dict:
    """Verify a locally signed Lattice Cast access JWT."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[LOCAL_ALGORITHM])


async def verify_authentik_token(token: str) -> dict:
    """Verify Authentik JWT token using JWKS."""
    jwks = await get_jwks("authentik")
    payload = jwt.decode(
        token,
        jwks,
        algorithms=[ALGORITHM],
        audience=settings.authentik.client_id,
        issuer=settings.authentik.issuer,
    )
    return payload


async def verify_google_token(token: str) -> dict:
    """Verify Google access token by calling userinfo endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.google.userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token",
            )
        return resp.json()


async def verify_bearer_token(
    authorization: str | None = Header(None),
) -> dict:
    """
    Verify token from Authorization header.
    Tries a locally signed Lattice Cast JWT first, then Authentik JWT,
    then Google userinfo. Returns token payload with _provider field.
    """
    total_start = time.time()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()
    expired = False

    # Try a locally signed Lattice Cast JWT first.
    try:
        logger.debug("Trying local token verification...")
        payload = verify_local_token(token)
        logger.info(f"Local verification: {time.time() - total_start:.3f}s")
        payload["_provider"] = "none"
        return payload
    except ExpiredSignatureError:
        logger.debug("Local token expired")
        expired = True
    except JWTError as e:
        logger.debug(f"Local verification failed: {e}")

    # Try Authentik (JWT)
    try:
        logger.debug("Trying Authentik token verification...")
        payload = await verify_authentik_token(token)
        logger.info(f"Authentik verification: {time.time() - total_start:.3f}s")
        payload["_provider"] = "authentik"
        return payload
    except ExpiredSignatureError:
        logger.debug("Authentik token expired")
        expired = True
    except JWTError as e:
        logger.debug(f"Authentik verification failed: {e}")
    except HTTPException:
        logger.debug("Authentik JWKS fetch failed")

    # Try Google (opaque token -> userinfo endpoint)
    try:
        logger.debug("Trying Google token verification...")
        userinfo = await verify_google_token(token)
        logger.info(f"Google verification: {time.time() - total_start:.3f}s")
        userinfo["_provider"] = "google"
        return userinfo
    except HTTPException as e:
        logger.debug(f"Google verification failed: {e.detail}")

    logger.warn(f"All providers failed after {time.time() - total_start:.3f}s")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token expired" if expired else "Invalid token",
    )
