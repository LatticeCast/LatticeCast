"""Issue Lattice Cast credentials shared by password login and first-party SSO.

This module is the sole issuer for locally signed access JWTs, central browser
sessions, and rotating refresh-token families. Verification remains in
``middleware.token`` because it is part of request authentication.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Response
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings

LOCAL_ALGORITHM = "HS256"
COOKIE_NAME = "lc_sso_session"
SESSION_TTL = timedelta(days=30)


def _utc_now() -> datetime:
    """Return a naive UTC timestamp for the project's TIMESTAMP convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def hash_refresh_token(refresh_token: str) -> str:
    """Only a SHA-256 digest of an opaque refresh token is persisted."""
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def create_lc_access_token(user_id: str, *, expires_minutes: int | None = None) -> tuple[str, int]:
    """Issue a locally signed Lattice Cast access JWT.

    Password login and first-party SSO issue this exact token format, so every
    existing authenticated API route accepts either flow without translation.
    """
    expires_delta = timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": user_id, "user_id": user_id, "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=LOCAL_ALGORITHM)
    return token, int(expires_delta.total_seconds())


async def create_browser_session(session: AsyncSession, user_id: UUID, auth_method: str) -> tuple[str, int]:
    """Create an opaque central-session cookie; only its SHA-256 hash reaches PG."""
    raw_token = secrets.token_urlsafe(48)
    expires_at = _utc_now() + SESSION_TTL
    await session.execute(
        text(
            "INSERT INTO private.sso_sessions "
            "(session_token_hash, user_id, auth_method, expires_at) "
            "VALUES (:token_hash, :user_id, :auth_method, :expires_at)"
        ),
        {
            "token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            "user_id": user_id,
            "auth_method": auth_method,
            "expires_at": expires_at,
        },
    )
    await session.commit()
    return raw_token, int(SESSION_TTL.total_seconds())


def set_browser_session_cookie(response: Response, raw_token: str, max_age: int) -> None:
    """Attach the central Lattice Cast SSO browser-session cookie."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.sso_cookie_secure,
        samesite="lax",
        path="/",
    )


async def issue_refresh_token(
    session: AsyncSession,
    user_id: UUID,
    *,
    family_id: UUID | None = None,
    session_id: UUID | None = None,
    commit: bool = True,
) -> str:
    """Persist and return one opaque, rotating Lattice Cast refresh token."""
    refresh_token = secrets.token_urlsafe(48)
    now = _utc_now()
    await session.execute(
        text(
            """
            INSERT INTO private.sso_refresh_tokens
                (token_hash, family_id, client_id, user_id, session_id, issued_at, expires_at)
            VALUES
                (:token_hash, :family_id, NULL, :user_id, :session_id, :issued_at, :expires_at)
            """
        ),
        {
            "token_hash": hash_refresh_token(refresh_token),
            "family_id": family_id or uuid4(),
            "user_id": user_id,
            "session_id": session_id,
            "issued_at": now,
            "expires_at": now + timedelta(days=settings.refresh_token_days),
        },
    )
    if commit:
        await session.commit()
    return refresh_token
