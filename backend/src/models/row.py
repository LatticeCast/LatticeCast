# src/models/row.py
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Row(SQLModel, table=True):
    """Row database model"""

    __tablename__ = "rows"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    table_id: UUID = Field(foreign_key="tables.id", index=True, description="Parent table ID")
    data: dict[str, Any] = Field(default_factory=dict, description="Row data keyed by column UUID (JSONB)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class RowCreate(SQLModel):
    data: dict[str, Any] = Field(default_factory=dict, description="Row data keyed by column UUID")


class RowUpdate(SQLModel):
    data: dict[str, Any] = Field(..., description="Row data keyed by column UUID (full replace)")


class RowResponse(SQLModel):
    id: UUID = Field(..., description="Unique identifier")
    table_id: UUID = Field(..., description="Parent table ID")
    data: dict[str, Any] = Field(..., description="Row data keyed by column UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
