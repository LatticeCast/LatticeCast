# src/models/table_view.py
# V34: simplified shape — single (workspace_id, table_id, name) PK.
# `type` discriminates the row purpose:
#   - 'schema' (name='__schema__'): config is the column array
#   - 'order'  (name='__order__'):  config is the ordered name array
#   - 'table' | 'kanban' | 'timeline' | 'dashboard' (user-given names):
#                                  config is the view-specific config blob
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKeyConstraint
from sqlmodel import Field, SQLModel

# Reserved row names — these encode meta-rows, not user views.
SCHEMA_ROW_NAME = "__schema__"
ORDER_ROW_NAME = "__order__"
RESERVED_NAMES = {SCHEMA_ROW_NAME, ORDER_ROW_NAME}

# Allowed view types for user-created views.
USER_VIEW_TYPES = ("table", "kanban", "timeline", "dashboard")


class TableView(SQLModel, table=True):
    """Row in public.table_views — see module docstring for type semantics."""

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
    name: str = Field(primary_key=True)
    type: str = Field(default="table")
    config: dict[str, Any] | list[Any] = Field(default_factory=dict, sa_type=JSON)
    created_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    updated_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
