# src/models/table_view.py
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class TableView(SQLModel, table=True):
    """View row in public.table_views — linked-list ordering via next_view_id."""

    __tablename__ = "table_views"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "table_id"],
            ["tables.workspace_id", "tables.table_id"],
            name="table_views_table_fkey",
        ),
    )

    workspace_id: UUID = Field(primary_key=True)
    table_id: str = Field(primary_key=True)
    view_number: int = Field(default=0, primary_key=True)
    is_default: bool = Field(default=False)
    next_view_id: int | None = Field(default=None)
    name: str = Field(...)
    type: str = Field(default="table")
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    updated_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
