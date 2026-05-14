# src/models/table.py
# V34: Table is identity-only. Columns moved to the __schema__ row in
# public.table_views; views moved to user-named rows in the same table.
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class Table(SQLModel, table=True):
    """Table identity — (workspace_id, table_id) composite PK."""

    __tablename__ = "tables"

    workspace_id: UUID = Field(
        primary_key=True,
        foreign_key="workspaces.workspace_id",
        description="Workspace UUID (composite PK)",
    )
    table_id: str = Field(primary_key=True, description="Table name (composite PK)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TableCreate(SQLModel):
    """Schema for creating a table."""

    table_id: str = Field(..., description="Table name (becomes the PK)")
    workspace_id: str | None = Field(default=None, description="Target workspace UUID or workspace_name")


class TableResponse(SQLModel):
    """Table identity + full schema snapshot (V44+ public.table_schemas).
    Every mutation endpoint also returns the schema fields below, so FE
    has a single shape to consume."""

    workspace_id: UUID
    table_id: str
    columns: list[dict[str, Any]] = Field(default_factory=list)
    view_order: list[str] = Field(
        default_factory=list,
        description="Display order of user views (subset of table_views.name).",
    )
    default_view: str | None = Field(
        default=None,
        description="Default view name; 'Schema' for the implicit pinned tab.",
    )
    views: list[dict[str, Any]] = Field(
        default_factory=list,
        description="User view rows ordered by view_order: {name, type, config}.",
    )
    created_at: datetime
    updated_at: datetime


class TableUpdate(SQLModel):
    """Rename a table_id."""

    table_id: str = Field(..., description="New table name")
