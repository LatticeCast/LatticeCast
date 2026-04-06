# src/models/workspace.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

MemberRoleType = Literal["owner", "member"]


class Workspace(SQLModel, table=True):
    """Workspace database model"""

    __tablename__ = "workspaces"

    workspace_id: UUID = Field(default_factory=uuid4, primary_key=True, description="UUID primary key")
    workspace_name: str = Field(description="Workspace display name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class WorkspaceMember(SQLModel, table=True):
    """Workspace member database model (composite PK)"""

    __tablename__ = "workspace_members"

    workspace_id: UUID = Field(primary_key=True, foreign_key="workspaces.workspace_id", description="Workspace UUID")
    user_id: UUID = Field(primary_key=True, foreign_key="users.user_id", description="User UUID")
    role: str = Field(default="member", description="Member role (owner/member)")


class WorkspaceCreate(SQLModel):
    """Schema for creating a workspace"""

    workspace_name: str = Field(..., description="Workspace display name")


class WorkspaceResponse(SQLModel):
    """Workspace response schema"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    workspace_name: str = Field(..., description="Workspace display name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workspace_id": "00000000-0000-0000-0000-000000000000",
                    "workspace_name": "My Workspace",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ]
        }
    }


class MemberCreate(SQLModel):
    """Schema for adding a workspace member — provide ONE of user_id, user_name, user_email"""

    user_id: UUID | None = Field(default=None, description="User UUID")
    user_name: str | None = Field(default=None, description="User display_id (e.g. lattice)")
    user_email: str | None = Field(default=None, description="User email")
    role: MemberRoleType = Field(default="member", description="Member role")


class MemberResponse(SQLModel):
    """Workspace member response schema"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: UUID = Field(..., description="User UUID")
    role: MemberRoleType = Field(..., description="Member role")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workspace_id": "00000000-0000-0000-0000-000000000000",
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "role": "owner",
                }
            ]
        }
    }
