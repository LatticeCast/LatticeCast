# src/models/view.py
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, TypeAdapter, ValidationError


class WidgetBinding(BaseModel):
    x: str | None = None
    y: str | None = None
    label: str | None = None
    value: str | None = None


class Widget(BaseModel):
    title: str
    chart: Literal["number", "bar", "pie", "line", "list"]
    lql: str
    binding: WidgetBinding = Field(default_factory=WidgetBinding)


class DashboardLayoutItem(BaseModel):
    widget_id: str
    x: int
    y: int
    w: int
    h: int


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["table"] = "table"


class KanbanConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["kanban"] = "kanban"


class TimelineConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["timeline"] = "timeline"


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["dashboard"] = "dashboard"
    layout: list[DashboardLayoutItem] = Field(default_factory=list)
    widgets: dict[str, Widget] = Field(default_factory=dict)


ViewConfig = Annotated[
    TableConfig | KanbanConfig | TimelineConfig | DashboardConfig,
    Discriminator("type"),
]

_adapter: TypeAdapter[ViewConfig] = TypeAdapter(ViewConfig)


def validate_view_config(view_type: str, config: dict[str, Any]) -> None:
    """Validate config dict against the ViewConfig schema for the given type.

    Merges type into the config dict so the discriminated union can select
    the right model. Raises ValueError with a human-readable message on failure.
    """
    merged = {"type": view_type, **config}
    try:
        _adapter.validate_python(merged)
    except ValidationError as e:
        msgs = [err.get("msg", str(err)) for err in e.errors()]
        raise ValueError("; ".join(msgs)) from e


class ViewCreate(BaseModel):
    """Request body for POST /tables/{tid}/views"""

    name: str
    type: str = "table"
    config: dict[str, Any] = Field(default_factory=dict)
