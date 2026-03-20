# src/models/table.py
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Table(SQLModel, table=True):
    """Table database model"""

    __tablename__ = "tables"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier")
    user_id: str = Field(index=True, description="Owner user ID (email)")
    name: str = Field(description="Table name")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class TableCreate(SQLModel):
    """Schema for creating a table"""

    name: str = Field(..., description="Table name")


class TableResponse(SQLModel):
    """Table response model for API"""

    id: UUID = Field(..., description="Unique identifier")
    user_id: str = Field(..., description="Owner user ID (email)")
    name: str = Field(..., description="Table name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TableUpdate(SQLModel):
    """Schema for updating a table"""

    name: str = Field(..., description="New table name")
