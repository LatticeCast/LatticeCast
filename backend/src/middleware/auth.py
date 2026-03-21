# src/middleware/auth.py
"""
User authentication middleware.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_session
from middleware.token import verify_bearer_token
from models.user import User
from util import logger


async def get_current_user(
    token_payload: dict = Depends(verify_bearer_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Middleware: Verify token and check user exists in database.
    Returns the User object if found.
    """
    email = token_payload.get("email")
    if not email:
        logger.warn("Token does not contain email")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain email",
        )

    result = await session.execute(select(User).where(User.user_id == email))
    user = result.scalar_one_or_none()

    if not user:
        if not settings.auth_required:
            # Auto-create user in no-auth mode
            user = User(user_id=email, role="user")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Auto-created user: {email}")
        else:
            logger.warn(f"User not registered: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not registered",
            )

    # Attach token payload to user for access to provider info
    user._token_payload = token_payload
    logger.debug(f"Authenticated user: {email} (role={user.role})")
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
