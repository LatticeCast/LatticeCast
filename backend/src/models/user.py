# src/models/user.py
from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

RoleType = Literal["user", "admin"]


class User(SQLModel, table=True):
    """User database model"""

    __tablename__ = "users"

    user_id: str = Field(primary_key=True, description="Email address (unique identifier)")
    name: str = Field(default="", description="Display name")
    role: str = Field(default="user", index=True, description="User role (user/admin)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserResponse(SQLModel):
    """User response model for API"""

    user_id: str = Field(..., description="Email address")
    name: str = Field(..., description="Display name")
    role: RoleType = Field(..., description="User role")

    model_config = {
        "json_schema_extra": {
            "examples": [{"user_id": "user@example.com", "name": "User", "role": "user"}]
        }
    }
