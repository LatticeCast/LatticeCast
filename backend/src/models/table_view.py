# src/models/table_view.py
#
# V44+: public.table_views holds ONLY user-view rows. The previous
# __schema__/__order__ meta rows have been moved into public.table_schemas
# (separate table). A CHECK constraint on table_views enforces that
# `name NOT IN ('__schema__','__order__') AND type IN USER_VIEW_TYPES`.
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKeyConstraint
from sqlmodel import Field, SQLModel

# FE display name for the always-pinned implicit first tab (rendered by
# the FE from public.table_schemas.config.columns; no DB row).
SCHEMA_VIEW_DISPLAY_NAME = "Schema"

# Allowed view types for user-created views.
USER_VIEW_TYPES = ("table", "kanban", "timeline", "dashboard")


class TableView(SQLModel, table=True):
    """Row in public.table_views — user views only after V44."""

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
