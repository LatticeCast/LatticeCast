# src/models/workspace.py
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

ActionType = Literal["read", "write", "owner"]


class Workspace(SQLModel, table=True):
    """Workspace database model"""

    __tablename__ = "workspaces"

    workspace_id: UUID = Field(default_factory=uuid4, primary_key=True, description="UUID primary key")
    workspace_name: str = Field(description="Workspace display name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class WorkspaceMember(SQLModel, table=True):
    """Workspace action-grant row (composite PK: workspace_id, user_id, action) — V33.

    One row per granted action, NOT one row per member: a member with
    'write' access has two rows (read + write), an owner has three
    (read + write + owner). Owner is materialized this way rather than
    encoded via hierarchy logic so every RLS check on this table (and
    on tables/rows/table_views/workspaces) stays a flat equality
    lookup. Use `repository.workspace.WorkspaceRepository` helpers
    (which aggregate rows into a single level per member) rather than
    querying this model directly for member-facing responses.
    """

    __tablename__ = "workspace_members"

    workspace_id: UUID = Field(primary_key=True, foreign_key="workspaces.workspace_id", description="Workspace UUID")
    user_id: UUID = Field(primary_key=True, foreign_key="auth.users.user_id", description="User UUID")
    action: str = Field(primary_key=True, description="Granted action (read/write/owner)")


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
    user_name: str | None = Field(default=None, description="User user_name (e.g. lattice)")
    user_email: str | None = Field(default=None, description="User email")
    level: ActionType = Field(
        default="write", description="Access level — implies every action at or below it (owner ⊇ write ⊇ read)"
    )


class MemberResponse(SQLModel):
    """Workspace member response schema"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: UUID = Field(..., description="User UUID")
    level: ActionType = Field(..., description="Access level (highest of the member's granted actions)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workspace_id": "00000000-0000-0000-0000-000000000000",
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "level": "owner",
                }
            ]
        }
    }


class MemberFullResponse(SQLModel):
    """Workspace member response with user_name and email joined from auth tables"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: UUID = Field(..., description="User UUID")
    user_name: str | None = Field(default=None, description="User handle from user_info")
    email: str | None = Field(default=None, description="User email from auth.gdpr")
    level: ActionType = Field(..., description="Access level (highest of the member's granted actions)")


class MemberLevelUpdate(SQLModel):
    """Schema for updating a member's access level"""

    level: ActionType = Field(..., description="New access level (read/write/owner)")
