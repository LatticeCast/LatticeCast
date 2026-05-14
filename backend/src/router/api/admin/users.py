# router/admin/users.py
#
# v40: PII (email) + handle (user_name) + config all live in
# gdpr.user_info. No more separate auth.gdpr table.

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session, get_session
from middleware.auth import require_admin
from models.user import User, UserInfo, UserResponse
from repository.user import UserRepository, bootstrap_user

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


RoleType = Literal["user", "admin"]


class UserCreate(BaseModel):
    email: str = Field(..., description="User email address (used as unique identifier)")
    role: RoleType = Field(default="user", description="User role")
    user_name: str | None = Field(default=None, description="Optional handle; auto-slugged from email if omitted")

    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com", "role": "user"}]}}


class UserUpdate(BaseModel):
    role: RoleType | None = Field(default=None, description="New role for the user")

    model_config = {"json_schema_extra": {"examples": [{"role": "admin"}]}}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int = Field(..., description="Total number of users")
    offset: int
    limit: int


async def _build_response(user: User, session: AsyncSession) -> UserResponse:
    info_res = await session.execute(select(UserInfo).where(UserInfo.user_id == user.user_id))
    info = info_res.scalar_one_or_none()
    return UserResponse(
        user_id=user.user_id,
        email=info.email if info else "",
        role=user.role,  # type: ignore[arg-type]
        user_name=info.user_name if info else None,
        config=info.config if info and info.config else {},
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    login_session: AsyncSession = Depends(get_login_session),
):
    """Create a new user (bootstraps auth.users + gdpr.user_info + workspace)."""
    existing = await UserRepository(login_session).get_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    user = await bootstrap_user(
        login_session=login_session,
        app_session=session,
        email=data.email,
        role=data.role,
        user_name=data.user_name,
    )
    return await _build_response(user, session)


@router.get("", response_model=UserListResponse)
async def list_users(
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of records to return"),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    count_result = await session.execute(select(func.count()).select_from(User))
    total = count_result.scalar() or 0

    result = await session.execute(select(User).offset(offset).limit(limit))
    users = result.scalars().all()

    out = [await _build_response(u, session) for u in users]
    return UserListResponse(users=out, total=total, offset=offset, limit=limit)


@router.get("/{user_email}", response_model=UserResponse)
async def get_user(
    user_email: str,
    session: AsyncSession = Depends(get_session),
):
    user = await UserRepository(session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _build_response(user, session)


@router.put("/{user_email}", response_model=UserResponse)
async def update_user(
    user_email: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_session),
):
    user = await UserRepository(session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if data.role is not None:
        user.role = data.role
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return await _build_response(user, session)


@router.delete("/{user_email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_email: str,
    login_session: AsyncSession = Depends(get_login_session),
):
    """Delete user by email (cascades to gdpr.user_info, workspace_members)."""
    user = await UserRepository(login_session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await login_session.delete(user)
    await login_session.commit()
