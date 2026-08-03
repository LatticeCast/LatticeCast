# src/middleware/token.py
"""
Token verification for OAuth providers.
"""

import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Header, HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from config.settings import settings
from middleware.jwks import get_jwks
from util import logger

ALGORITHM = "RS256"
LOCAL_ALGORITHM = "HS256"


def create_access_token(user_id: str) -> tuple[str, int]:
    """Issue a self-signed JWT for the password-login flow.

    Returns (token, expires_in_seconds).
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": user_id, "user_id": user_id, "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=LOCAL_ALGORITHM)
    return token, int(expires_delta.total_seconds())


def verify_local_token(token: str) -> dict:
    """Verify a self-issued JWT (password-login flow)."""
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
    Tries our own signed JWT (password-login) first, then Authentik JWT,
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

    # Try our own JWT first (password-login flow)
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
