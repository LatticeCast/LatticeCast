# src/models/view.py
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field


class LayoutEntry(BaseModel):
    id: str
    x: int
    y: int
    w: int
    h: int


class ChartBlock(BaseModel):
    kind: Literal["chart"] = "chart"
    title: str
    lql: str
    echarts: dict[str, Any] = Field(default_factory=dict)


class NumberBlock(BaseModel):
    kind: Literal["number"] = "number"
    title: str
    lql: str
    field: str
    format: str | None = None


class ListColumn(BaseModel):
    key: str
    label: str


class ListBlock(BaseModel):
    kind: Literal["list"] = "list"
    title: str
    lql: str
    columns: list[ListColumn] = Field(default_factory=list)


Block = Annotated[
    ChartBlock | NumberBlock | ListBlock,
    Discriminator("kind"),
]


class ViewCreate(BaseModel):
    """Request body for POST /tables/{tid}/views"""

    name: str
    type: str = "table"
    config: dict[str, Any] = Field(default_factory=dict)
