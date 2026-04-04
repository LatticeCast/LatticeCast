# src/models/user.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

RoleType = Literal["user", "admin"]


class User(SQLModel, table=True):
    """User database model"""

    __tablename__ = "users"

    user_id: UUID = Field(default_factory=uuid4, primary_key=True, description="UUID primary key")
    email: str = Field(index=True, description="Email address (unique identifier)")
    name: str = Field(default="", description="Display name")
    role: str = Field(default="user", index=True, description="User role (user/admin)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserInfo(SQLModel, table=True):
    """User info table — display_id lookup and profile metadata"""

    __tablename__ = "user_info"

    user_id: UUID = Field(
        primary_key=True, foreign_key="users.user_id", description="UUID FK → users"
    )
    display_id: str = Field(index=True, description="URL-safe slug (unique)")
    email: str = Field(default="", description="Email address (denormalized for display)")
    name: str = Field(default="", description="Display name")


class UserResponse(SQLModel):
    """User response model for API"""

    user_id: UUID = Field(..., description="UUID identifier")
    email: str = Field(..., description="Email address")
    name: str = Field(..., description="Display name")
    role: RoleType = Field(..., description="User role")
    display_id: str | None = Field(default=None, description="URL-safe slug from user_info")

    model_config = {
        "json_schema_extra": {
            "examples": [{"user_id": "00000000-0000-0000-0000-000000000000", "email": "user@example.com", "name": "User", "role": "user", "display_id": "user-example-com"}]
        }
    }
