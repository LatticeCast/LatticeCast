# src/models/user.py
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
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
    """User PII + handle + per-user UI config — gdpr.user_info.

    v40: merged the old public.user_info + auth.gdpr split into one
    table in the gdpr schema. A GDPR delete drops this row (or the
    whole schema) without touching auth.users / workspaces."""

    __tablename__ = "user_info"
    __table_args__ = {"schema": "gdpr"}

    user_id: UUID = Field(primary_key=True, foreign_key="auth.users.user_id", description="UUID FK → auth.users")
    email: str = Field(unique=True, description="Email address (unique)")
    user_name: str = Field(index=True, unique=True, description="URL-safe slug (unique)")
    config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("config", JSONB, nullable=False, server_default="{}"),
        description="Per-user UI config blob (darkMode, lastView per table, …)",
    )


class UserPassword(SQLModel, table=True):
    """Optional password-login credential — gdpr.user_password.

    Kept out of gdpr.user_info: that table has a broad app_user SELECT
    policy (V20, needed to resolve other users by email/user_name for
    workspace invites) which would expose password_hash to every one of
    those reads. This table has no grants to app at all — only
    mgr_user (login_session, BYPASSRLS) touches it, and only via
    password_login / set_me_password, both scoped to the caller's own
    user_id. No row for a user = no password set.
    """

    __tablename__ = "user_password"
    __table_args__ = {"schema": "gdpr"}

    user_id: UUID = Field(primary_key=True, foreign_key="gdpr.user_info.user_id", description="UUID FK → user_info")
    password_hash: str = Field(description="Bcrypt hash")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class UserResponse(SQLModel):
    """User response model for API"""

    user_id: UUID = Field(..., description="UUID identifier")
    email: str = Field(default="", description="Email (from gdpr.user_info)")
    role: RoleType = Field(..., description="User role")
    user_name: str | None = Field(default=None, description="Public handle from gdpr.user_info")
    config: dict[str, Any] = Field(default_factory=dict, description="Per-user UI config blob")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "email": "user@example.com",
                    "role": "user",
                    "user_name": "user",
                }
            ]
        }
    }
