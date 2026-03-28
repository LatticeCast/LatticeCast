# src/models/workspace.py
from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

MemberRoleType = Literal["owner", "member"]


class Workspace(SQLModel, table=True):
    """Workspace database model"""

    __tablename__ = "workspaces"

    workspace_id: str = Field(primary_key=True, description="Workspace identifier (email for default workspace)")
    name: str = Field(description="Workspace display name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class WorkspaceMember(SQLModel, table=True):
    """Workspace member database model (composite PK)"""

    __tablename__ = "workspace_members"

    workspace_id: str = Field(primary_key=True, foreign_key="workspaces.workspace_id", description="Workspace identifier")
    user_id: str = Field(primary_key=True, foreign_key="users.user_id", description="User identifier (email)")
    role: str = Field(default="member", description="Member role (owner/member)")


class WorkspaceCreate(SQLModel):
    """Schema for creating a workspace"""

    name: str = Field(..., description="Workspace display name")


class WorkspaceResponse(SQLModel):
    """Workspace response schema"""

    workspace_id: str = Field(..., description="Workspace identifier")
    name: str = Field(..., description="Workspace display name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [{"workspace_id": "user@example.com", "name": "user@example.com", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}]
        }
    }


class MemberCreate(SQLModel):
    """Schema for adding a workspace member"""

    user_id: str = Field(..., description="User identifier (email)")
    role: MemberRoleType = Field(default="member", description="Member role")


class MemberResponse(SQLModel):
    """Workspace member response schema"""

    workspace_id: str = Field(..., description="Workspace identifier")
    user_id: str = Field(..., description="User identifier (email)")
    role: MemberRoleType = Field(..., description="Member role")

    model_config = {
        "json_schema_extra": {
            "examples": [{"workspace_id": "user@example.com", "user_id": "user@example.com", "role": "owner"}]
        }
    }
