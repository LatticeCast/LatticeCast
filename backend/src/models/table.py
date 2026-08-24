# src/models/table.py
# V34: Table is identity-only. Columns moved to the __schema__ row in
# public.table_views; views moved to user-named rows in the same table.
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

ColumnType = Literal["text", "string", "number", "date", "select", "tags", "checkbox", "url", "blob"]
BlobKind = Literal["file", "image", "doc", "table"]


class ColumnOptions(SQLModel):
    """Column options shared by the column mutation API and frontend contract.

    Blob values describe one stored file. Deliberately omit a `multiple` option
    so the contract cannot represent a multi-file blob cell.
    """

    model_config = ConfigDict(extra="forbid")

    # Existing tables may carry either the legacy {label} or current
    # {value, color} choice shape, so preserve choices as opaque JSON.
    choices: list[dict[str, Any]] | None = None
    width: int | None = None
    kind: BlobKind | None = Field(
        default=None,
        description="Blob UI hint: file=any binary, image=image, doc=Markdown, table=CSV/XLSX/JSONL.",
    )
    accept: str | None = Field(
        default=None,
        description="Optional HTML file-input accept hint. It does not enforce server-side MIME validation.",
    )


class ColumnCreate(SQLModel):
    name: str
    type: ColumnType = "text"
    options: ColumnOptions = Field(default_factory=ColumnOptions)


class ColumnUpdate(SQLModel):
    name: str | None = None
    type: ColumnType | None = None
    options: ColumnOptions | None = None


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
    view_order: list[int] = Field(
        default_factory=list,
        description="Display order of user views — list of view_id BIGINTs.",
    )
    default_view: int = Field(
        default=0,
        description="Default view_id (BIGINT); 0 means the implicit Schema tab.",
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
