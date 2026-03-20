# src/models/column.py
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

ColumnType = Literal["text", "number", "date", "select", "checkbox", "url"]


class Column(SQLModel, table=True):
    """Column database model"""

    __tablename__ = "columns"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    table_id: UUID = Field(foreign_key="tables.id", index=True, description="Parent table ID")
    name: str = Field(description="Column name")
    type: str = Field(description="Column type (text, number, date, select, checkbox, url)")
    options: dict[str, Any] = Field(default_factory=dict, description="Type-specific options (JSONB)")
    position: int = Field(default=0, description="Display order")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")


class ColumnCreate(SQLModel):
    name: str = Field(..., description="Column name")
    type: ColumnType = Field(..., description="Column type")
    options: dict[str, Any] = Field(default_factory=dict, description="Type-specific options")
    position: int = Field(default=0, description="Display order")


class ColumnUpdate(SQLModel):
    name: str | None = Field(default=None, description="Column name")
    type: ColumnType | None = Field(default=None, description="Column type")
    options: dict[str, Any] | None = Field(default=None, description="Type-specific options")
    position: int | None = Field(default=None, description="Display order")


class ColumnResponse(SQLModel):
    id: UUID = Field(..., description="Unique identifier")
    table_id: UUID = Field(..., description="Parent table ID")
    name: str = Field(..., description="Column name")
    type: str = Field(..., description="Column type")
    options: dict[str, Any] = Field(..., description="Type-specific options")
    position: int = Field(..., description="Display order")
    created_at: datetime = Field(..., description="Creation timestamp")
