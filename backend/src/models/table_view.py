# src/models/table_view.py
#
# v40: public.table_views holds user-view rows ONLY. View identity is the
# composite PK (workspace_id, table_id, view_id BIGINT). view_id is
# auto-assigned by a BEFORE INSERT trigger (V9 + V16). Display name and
# view type live inside the `config` JSONB blob:
#
#   {"name": "Sprint Board", "type": "kanban", "group_by": "...", ...}
#
# This mirrors how columns identify themselves: by column_id (UUID),
# with name + type + options stored alongside.
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# FE display name for the always-pinned implicit first tab (rendered by
# the FE from public.table_schemas.config.columns; no DB row).
SCHEMA_VIEW_DISPLAY_NAME = "Schema"

# Allowed view types for user-created views (stored in config.type).
USER_VIEW_TYPES = ("table", "kanban", "timeline", "dashboard")


class TableView(SQLModel, table=True):
    """Row in public.table_views — user views only.

    Identifier: view_id (BIGINT, auto-assigned per (workspace_id, table_id)).
    Display name and type live inside `config`, not as separate columns.
    """

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
    view_id: int = Field(default=0, primary_key=True)
    config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("config", JSONB, nullable=False, server_default="{}"),
    )
    created_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    updated_by: UUID | None = Field(default=None, foreign_key="auth.users.user_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def name(self) -> str:
        """View display name, extracted from config."""
        return str(self.config.get("name", ""))

    @property
    def type(self) -> str:
        """View type (table/kanban/timeline/dashboard), extracted from config."""
        return str(self.config.get("type", "table"))
