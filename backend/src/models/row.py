# src/models/row.py
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class Row(SQLModel, table=True):
    """Row database model — PK is (table_id, row_id).

    The workspace is the parent table's; a row does not carry a second copy of
    it, so the two values cannot disagree and RLS authorises on table_id.
    """

    __tablename__ = "rows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["table_id"],
            ["tables.table_id"],
            name="rows_table_fkey",
        ),
    )

    table_id: int = Field(
        primary_key=True, sa_type=BigInteger, description="Parent table identity (composite PK/FK)"
    )
    row_id: int = Field(
        default=0,
        primary_key=True,
        sa_type=BigInteger,
        description="Auto-increment row number per table (set by DB trigger)",
    )
    row_data: dict[str, Any] = Field(
        default_factory=dict, sa_type=JSON, description="Row data keyed by column UUID (JSONB)"
    )
    created_by: UUID | None = Field(
        default=None, foreign_key="auth.users.user_id", description="UUID of user who created the row"
    )
    updated_by: UUID | None = Field(
        default=None, foreign_key="auth.users.user_id", description="UUID of user who last updated the row"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last update timestamp")


class RowCreate(SQLModel):
    row_data: dict[str, Any] = Field(default_factory=dict, description="Row data keyed by column UUID")


class RowUpdate(SQLModel):
    row_data: dict[str, Any] = Field(
        ..., description="Partial row data to merge into existing row_data (unset fields are preserved)"
    )


class RowPut(SQLModel):
    row_data: dict[str, Any] = Field(
        ..., description="Complete non-blob row data; unspecified non-blob cells are removed"
    )


class RowResponse(SQLModel):
    table_id: int = Field(..., description="Parent table identity")
    row_id: int = Field(..., description="Auto-increment row number per table")
    row_data: dict[str, Any] = Field(..., description="Row data keyed by column UUID")
    created_by: UUID | None = Field(default=None, description="UUID of user who created the row")
    updated_by: UUID | None = Field(default=None, description="UUID of user who last updated the row")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
