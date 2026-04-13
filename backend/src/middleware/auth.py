# src/middleware/auth.py
"""
User authentication middleware.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_session
from middleware.token import verify_bearer_token
from models.user import User
from repository.user import UserRepository
from util import logger


async def get_current_user(
    token_payload: dict = Depends(verify_bearer_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Middleware: Verify token and check user exists in database.
    Returns the User object if found.
    """
    user_id_str = token_payload.get("user_id")
    email = token_payload.get("email")

    if user_id_str:
        # No-auth mode: resolve by UUID or user_name
        user = await UserRepository(session).resolve_user(user_id_str)
        if not user:
            if not settings.auth_required:
                user = await UserRepository(session).create(user_id_str)
                logger.info(f"Auto-created user: {user_id_str}")
            else:
                logger.warn(f"User not found: {user_id_str}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User not registered",
                )
        logger.debug(f"Authenticated user: {user.user_id} via user_id token (role={user.role})")
    elif email:
        from models.user import UserInfo
        result = await session.execute(
            select(User).join(UserInfo, User.user_id == UserInfo.user_id).where(UserInfo.email == email)
        )
        user = result.scalar_one_or_none()
        if not user:
            if not settings.auth_required:
                user = await UserRepository(session).create(email)
                logger.info(f"Auto-created user: {email}")
            else:
                logger.warn(f"User not registered: {email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User not registered",
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
    """
    FastAPI dependency — app session with PG RLS user context set.

    Uses session-level SET (not SET LOCAL) so the context survives the
    intermediate session.commit() calls in our repository methods.
    The RESET in the finally block clears the context before the connection
    returns to the pool, preventing leakage to subsequent requests.
    """
    # SET doesn't support bind params in asyncpg — use f-string (safe: user_id is a validated UUID)
    uid = str(user.user_id).replace("'", "")
    await session.execute(text(f"SET app.current_user_id = '{uid}'"))
    try:
        yield session
    finally:
        try:
            await session.execute(text("RESET app.current_user_id"))
        except Exception:
            pass


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
