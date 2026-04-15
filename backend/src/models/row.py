# src/models/row.py
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class Row(SQLModel, table=True):
    """Row database model — PK is (workspace_id, table_id, row_number)"""

    __tablename__ = "rows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "table_id"],
            ["tables.workspace_id", "tables.table_id"],
            name="rows_table_fkey",
        ),
    )

    workspace_id: UUID = Field(primary_key=True, description="Workspace UUID (composite PK/FK)")
    table_id: str = Field(primary_key=True, description="Parent table ID (composite PK/FK)")
    row_number: int = Field(default=0, primary_key=True, description="Auto-increment row number per table (set by DB trigger)")
    row_data: dict[str, Any] = Field(default_factory=dict, sa_type=JSON, description="Row data keyed by column UUID (JSONB)")
    created_by: UUID | None = Field(default=None, foreign_key="users.user_id", description="UUID of user who created the row")
    updated_by: UUID | None = Field(default=None, foreign_key="users.user_id", description="UUID of user who last updated the row")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class RowCreate(SQLModel):
    row_data: dict[str, Any] = Field(default_factory=dict, description="Row data keyed by column UUID")


class RowUpdate(SQLModel):
    row_data: dict[str, Any] = Field(..., description="Partial row data to merge into existing row_data (unset fields are preserved)")


class RowResponse(SQLModel):
    workspace_id: UUID = Field(..., description="Workspace UUID")
    table_id: str = Field(..., description="Parent table ID (string)")
    row_number: int = Field(..., description="Auto-increment row number per table")
    row_data: dict[str, Any] = Field(..., description="Row data keyed by column UUID")
    created_by: UUID | None = Field(default=None, description="UUID of user who created the row")
    updated_by: UUID | None = Field(default=None, description="UUID of user who last updated the row")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
