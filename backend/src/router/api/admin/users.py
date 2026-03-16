# router/admin/users.py

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import require_admin
from models.user import User, UserResponse

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)

# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------

RoleType = Literal["user", "admin"]


class UserCreate(BaseModel):
    """Request body for creating a new user"""

    id: EmailStr = Field(..., description="User email address (used as unique identifier)")
    role: RoleType = Field(default="user", description="User role")

    model_config = {"json_schema_extra": {"examples": [{"id": "user@example.com", "role": "user"}]}}


class UserUpdate(BaseModel):
    """Request body for updating a user"""

    role: RoleType | None = Field(default=None, description="New role for the user")

    model_config = {"json_schema_extra": {"examples": [{"role": "admin"}]}}


class UserListResponse(BaseModel):
    """Paginated list of users"""

    users: list[UserResponse]
    total: int = Field(..., description="Total number of users")
    offset: int
    limit: int


# --------------------------------------------------
# ROUTES
# --------------------------------------------------


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new user by email"""
    result = await session.execute(select(User).where(User.id == data.id))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    user = User(id=data.id, role=data.role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get(
    "",
    response_model=UserListResponse,
)
async def list_users(
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of records to return"),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List all users (paginated)"""
    from sqlalchemy import func

    # Get total count
    count_result = await session.execute(select(func.count()).select_from(User))
    total = count_result.scalar()

    # Get paginated users
    result = await session.execute(select(User).offset(offset).limit(limit))
    users = result.scalars().all()

    return UserListResponse(
        users=users,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get user by email (id)"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
async def update_user(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update user role by email (id)"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if data.role is not None:
        user.role = data.role

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete user by email (id)"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await session.delete(user)
    await session.commit()
