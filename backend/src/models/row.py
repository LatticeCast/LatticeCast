# src/models/row.py
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class Row(SQLModel, table=True):
    """Row database model"""

    __tablename__ = "rows"

    row_id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    table_id: UUID = Field(foreign_key="tables.table_id", index=True, description="Parent table ID")
    row_data: dict[str, Any] = Field(default_factory=dict, sa_type=JSON, description="Row data keyed by column UUID (JSONB)")
    created_by: str = Field(default="", description="User ID who created the row")
    updated_by: str = Field(default="", description="User ID who last updated the row")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class RowCreate(SQLModel):
    row_data: dict[str, Any] = Field(default_factory=dict, description="Row data keyed by column UUID")


class RowUpdate(SQLModel):
    row_data: dict[str, Any] = Field(..., description="Row data keyed by column UUID (full replace)")


class RowResponse(SQLModel):
    row_id: UUID = Field(..., description="Unique identifier")
    table_id: UUID = Field(..., description="Parent table ID")
    row_data: dict[str, Any] = Field(..., description="Row data keyed by column UUID")
    created_by: str = Field(..., description="User ID who created the row")
    updated_by: str = Field(..., description="User ID who last updated the row")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
