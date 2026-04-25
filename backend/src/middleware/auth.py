# src/middleware/auth.py
"""
User authentication middleware.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_session
from middleware.token import verify_bearer_token
from models.user import User
from repository.user import UserRepository, resolve_user_by_email
from util import logger


async def get_current_user(
    token_payload: dict = Depends(verify_bearer_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Middleware: Verify token and check user exists in database.

    - `user_id` token (UUID or user_name) → resolved via app session.
    - `email` token → resolved via auth.gdpr (app session, SELECT granted in V32).

    Auto-creation in AUTH_REQUIRED=false mode is disabled: it races across
    multi-worker setups. Admins must bootstrap users via the admin API.
    TODO: consider an idempotent INSERT ON CONFLICT DO NOTHING path.
    """
    user_id_str = token_payload.get("user_id")
    email = token_payload.get("email")

    if user_id_str:
        user = await UserRepository(session).resolve_user(user_id_str)
        if not user:
            logger.warn(f"User not found: {user_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not registered — bootstrap required (auto-create disabled)",
            )
        logger.debug(f"Authenticated user: {user.user_id} via user_id token (role={user.role})")
    elif email:
        user = await resolve_user_by_email(email, session)
        if not user:
            logger.warn(f"User not registered: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not registered — bootstrap required (auto-create disabled)",
            )
        logger.debug(f"Authenticated user: {email} (role={user.role})")
    else:
        logger.warn("Token does not contain user_id or email")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain user_id or email",
        )

    # Attach token payload to user for access to provider info
    user._token_payload = token_payload
    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """
    Middleware: Require user to have admin role.
    """
    if user.role != "admin":
        logger.warn(f"Admin access denied for: {user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.debug(f"Admin access granted: {user.user_id}")
    return user


async def get_rls_session(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AsyncSession:
    """App session with PG RLS user context set via set_config.

    No manual reset: when the session closes and returns the connection to
    the asyncpg pool, the pool runs `DISCARD ALL` on release, which clears
    all session-level settings (incl. `app.current_user_id`). So the next
    request starts clean even if this one aborted.
    """
    uid = str(user.user_id)
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, false)").bindparams(uid=uid)
    )
    yield session


async def require_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    Middleware: Require user to have 'user' role (active subscription).
    """
    if user.role != "user":
        logger.warn(f"User access denied for: {user.user_id} (role={user.role})")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subscription required",
        )

    logger.debug(f"User access granted: {user.user_id}")
    return user
