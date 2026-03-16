# src/models/user.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

RoleType = Literal["user", "admin"]


class User(SQLModel, table=True):
    """User database model"""

    __tablename__ = "users"

    uuid: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    id: str = Field(unique=True, index=True, description="Email address (unique identifier)")
    role: str = Field(default="user", index=True, description="User role (user/admin)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserResponse(SQLModel):
    """User response model for API"""

    uuid: UUID = Field(..., description="Unique identifier")
    id: str = Field(..., description="Email address")
    role: RoleType = Field(..., description="User role")

    model_config = {
        "json_schema_extra": {
            "examples": [{"uuid": "550e8400-e29b-41d4-a716-446655440000", "id": "user@example.com", "role": "user"}]
        }
    }
