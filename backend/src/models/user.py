# src/models/user.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

RoleType = Literal["user", "admin"]


class User(SQLModel, table=True):
    """User identity core — auth.users"""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    user_id: UUID = Field(default_factory=uuid4, primary_key=True, description="UUID primary key")
    role: str = Field(default="user", index=True, description="User role (user/admin)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserInfo(SQLModel, table=True):
    """Public handle — public.user_info"""

    __tablename__ = "user_info"

    user_id: UUID = Field(primary_key=True, foreign_key="auth.users.user_id", description="UUID FK → auth.users")
    user_name: str = Field(index=True, unique=True, description="URL-safe slug (unique)")


class Gdpr(SQLModel, table=True):
    """PII — auth.gdpr (login_user role only)"""

    __tablename__ = "gdpr"
    __table_args__ = {"schema": "auth"}

    user_id: UUID = Field(primary_key=True, foreign_key="auth.users.user_id", description="UUID FK → auth.users")
    email: str = Field(unique=True, description="Email address (unique)")
    legal_name: str = Field(default="", description="Legal name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserResponse(SQLModel):
    """User response model for API"""

    user_id: UUID = Field(..., description="UUID identifier")
    email: str = Field(default="", description="Email (from auth.gdpr; requires login session)")
    legal_name: str = Field(default="", description="Legal name (from auth.gdpr)")
    role: RoleType = Field(..., description="User role")
    user_name: str | None = Field(default=None, description="Public handle from user_info")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "email": "user@example.com",
                    "legal_name": "User",
                    "role": "user",
                    "user_name": "user",
                }
            ]
        }
    }
