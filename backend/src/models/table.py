# src/models/table.py
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class Table(SQLModel, table=True):
    """Table database model"""

    __tablename__ = "tables"

    workspace_id: UUID = Field(index=True, foreign_key="workspaces.workspace_id", description="Workspace UUID (FK)")
    table_id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    table_name: str = Field(description="Table name")
    columns: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON, description="Column definitions")
    views: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON, description="View configurations")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class TableCreate(SQLModel):
    """Schema for creating a table"""

    table_name: str = Field(..., description="Table name")
    workspace_id: str | None = Field(
        default=None, description="Target workspace UUID or workspace_name (defaults to user's first workspace)"
    )


class TableResponse(SQLModel):
    """Table response model for API"""

    table_id: UUID = Field(..., description="Unique identifier")
    workspace_id: UUID = Field(..., description="Workspace UUID")
    table_name: str = Field(..., description="Table name")
    columns: list[dict[str, Any]] = Field(default_factory=list, description="Column definitions")
    views: list[dict[str, Any]] = Field(default_factory=list, description="View configurations")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TableUpdate(SQLModel):
    """Schema for updating a table"""

    table_name: str = Field(..., description="New table name")
