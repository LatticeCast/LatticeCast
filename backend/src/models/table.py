# src/models/table.py
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class Table(SQLModel, table=True):
    """Table database model — table_id is human-readable string PK (= table name)"""

    __tablename__ = "tables"

    workspace_id: UUID = Field(
        primary_key=True, foreign_key="workspaces.workspace_id", description="Workspace UUID (composite PK)"
    )
    table_id: str = Field(primary_key=True, description="Table name (composite PK with workspace_id)")
    columns: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON, description="Column definitions")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class TableCreate(SQLModel):
    """Schema for creating a table"""

    table_id: str = Field(..., description="Table name (becomes the PK)")
    workspace_id: str | None = Field(default=None, description="Target workspace UUID or workspace_name")


class TableResponse(SQLModel):
    """Table response model for API"""

    workspace_id: UUID = Field(..., description="Workspace UUID")
    table_id: str = Field(..., description="Table name (PK)")
    columns: list[dict[str, Any]] = Field(default_factory=list, description="Column definitions")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TableUpdate(SQLModel):
    """Schema for updating a table — rename table_id"""

    table_id: str = Field(..., description="New table name")
