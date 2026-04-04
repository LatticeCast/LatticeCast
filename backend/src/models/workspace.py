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
    display_id: str = Field(index=True, description="URL-safe slug derived from original workspace identifier")
    name: str = Field(description="Workspace display name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class WorkspaceInfo(SQLModel, table=True):
    """Workspace info table — display_id lookup and metadata"""

    __tablename__ = "workspace_info"

    workspace_id: UUID = Field(
        primary_key=True, foreign_key="workspaces.workspace_id", description="UUID FK → workspaces"
    )
    display_id: str = Field(index=True, description="URL-safe slug (unique)")
    name: str = Field(default="", description="Workspace display name")


class WorkspaceMember(SQLModel, table=True):
    """Workspace member database model (composite PK)"""

    __tablename__ = "workspace_members"

    workspace_id: UUID = Field(primary_key=True, foreign_key="workspaces.workspace_id", description="Workspace UUID")
    user_id: UUID = Field(primary_key=True, foreign_key="users.user_id", description="User UUID")
    role: str = Field(default="member", description="Member role (owner/member)")


class WorkspaceCreate(SQLModel):
    """Schema for creating a workspace"""

    name: str = Field(..., description="Workspace display name")


class WorkspaceResponse(SQLModel):
    """Workspace response schema"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    display_id: str | None = Field(default=None, description="URL-safe slug from workspace_info")
    name: str = Field(..., description="Workspace display name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workspace_id": "00000000-0000-0000-0000-000000000000",
                    "display_id": "my-workspace",
                    "name": "My Workspace",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ]
        }
    }


class MemberCreate(SQLModel):
    """Schema for adding a workspace member"""

    user_email: str = Field(..., description="User email address")
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
