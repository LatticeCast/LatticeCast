# router/admin/users.py
#
# v40: PII (email) + handle (user_name) + config all live in
# gdpr.user_info. No more separate auth.gdpr table.

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session, get_session
from models.user import User, UserInfo, UserPassword, UserResponse
from repository.user import UserRepository, bootstrap_user

router = APIRouter(prefix="/users", tags=["admin-users"])


RoleType = Literal["user", "admin"]


class UserCreate(BaseModel):
    email: str = Field(..., description="User email address (used as unique identifier)")
    role: RoleType = Field(default="user", description="User role")
    user_name: str | None = Field(default=None, description="Optional handle; auto-slugged from email if omitted")
    allow_no_pwd: bool = Field(
        default=False,
        description="True lets the account log in without a password. Otherwise it cannot log in until a password is set.",
    )

    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com", "role": "user"}]}}


class UserUpdate(BaseModel):
    role: RoleType | None = Field(default=None, description="New role for the user")

    # Unknown fields are rejected, so allow_no_pwd (create-time only) can never be
    # "accepted" here and silently ignored.
    model_config = {"extra": "forbid", "json_schema_extra": {"examples": [{"role": "admin"}]}}


class AllowNoPwdRequest(BaseModel):
    allow_no_pwd: bool = Field(
        ..., description="True: the account may log in without a password. False: it may not (until a password is set)."
    )


class AllowNoPwdResponse(BaseModel):
    user_id: UUID
    allow_no_pwd: bool


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
        allow_no_pwd=data.allow_no_pwd,
    )
    return await _build_response(user, login_session)


@router.get("", response_model=UserListResponse)
async def list_users(
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of records to return"),
    login_session: AsyncSession = Depends(get_login_session),
) -> UserListResponse:
    count_result = await login_session.execute(select(func.count()).select_from(User))
    total = count_result.scalar() or 0

    result = await login_session.execute(select(User).offset(offset).limit(limit))
    users = result.scalars().all()

    out = [await _build_response(u, login_session) for u in users]
    return UserListResponse(users=out, total=total, offset=offset, limit=limit)


@router.get("/{user_email}", response_model=UserResponse)
async def get_user(
    user_email: str,
    login_session: AsyncSession = Depends(get_login_session),
):
    user = await UserRepository(login_session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _build_response(user, login_session)


@router.put("/{user_email}", response_model=UserResponse)
async def update_user(
    user_email: str,
    data: UserUpdate,
    login_session: AsyncSession = Depends(get_login_session),
):
    user = await UserRepository(login_session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if data.role is not None:
        user.role = data.role
        login_session.add(user)
        await login_session.commit()
        await login_session.refresh(user)
    return await _build_response(user, login_session)


@router.put(
    "/{user_email}/allow-no-pwd",
    response_model=AllowNoPwdResponse,
    responses={409: {"description": "The account has a password"}},
)
async def set_allow_no_pwd(
    user_email: str,
    data: AllowNoPwdRequest,
    login_session: AsyncSession = Depends(get_login_session),
) -> AllowNoPwdResponse:
    """Let one account log in without a password, or stop it.

    Only an explicit TRUE opens passwordless login. An account that already has a
    password cannot be made passwordless (409): remove the password first.
    """
    user = await UserRepository(login_session).get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stored = (
        await login_session.execute(select(UserPassword).where(UserPassword.user_id == user.user_id))
    ).scalar_one_or_none()
    if data.allow_no_pwd:
        if stored is not None and stored.password_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account has a password; it cannot also be passwordless",
            )
        if stored is None:
            login_session.add(UserPassword(user_id=user.user_id, password_hash=None, allow_no_pwd=True))
        else:
            stored.allow_no_pwd = True
            login_session.add(stored)
    elif stored is not None and not stored.password_hash:
        stored.allow_no_pwd = None
        login_session.add(stored)
    await login_session.commit()
    return AllowNoPwdResponse(user_id=user.user_id, allow_no_pwd=bool(data.allow_no_pwd))


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
