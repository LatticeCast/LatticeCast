from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.table import TableResponse
from models.user import User
from repository.table import TableRepository
from repository.table_view import TableViewRepository
from repository.workspace import WorkspaceRepository

from ._shared import _CRM_COLUMNS, _PM_COLUMNS, _build_table_response

router = APIRouter(tags=["tables"])


def _build_columns(specs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    columns: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}
    for pos, spec in enumerate(specs):
        col_id = str(uuid4())
        columns.append(
            {
                "column_id": col_id,
                "name": spec["name"],
                "type": spec["type"],
                "options": spec.get("options", {}),
                "position": pos,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        name_to_id[spec["name"]] = col_id
    return columns, name_to_id


async def _resolve_template_workspace(data: dict[str, Any], user: User, ws_repo: WorkspaceRepository):
    raw_workspace = data.get("workspace_name") or data.get("workspace_id")
    if raw_workspace:
        workspace = await ws_repo.resolve_workspace(str(raw_workspace))
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if not await ws_repo.is_member(workspace.workspace_id, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of that workspace")
        return workspace.workspace_id
    workspace = await ws_repo.get_first_owned_workspace(user.user_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No workspace found — create a workspace first"
        )
    return workspace.workspace_id


@router.post("/template/pm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_pm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table_id = data.get("table_id", "") or data.get("table_name", "") or data.get("name", "")
    if not table_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="table_id is required")
    ws_repo = WorkspaceRepository(session)
    workspace_id = await _resolve_template_workspace(data, user, ws_repo)

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, table_id=table_id)

    columns, col_ids = _build_columns(_PM_COLUMNS)
    view_repo = TableViewRepository(session)
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    for col in columns:
        try:
            await table_repo.create_column_index(table.table_id, col["column_id"], col["type"])
        except Exception:
            # A failed CREATE INDEX poisons the transaction; rollback so
            # the rest of the request (views, set_order) can still run.
            await session.rollback()

    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Sprint Board",
        view_type="kanban",
        config={
            "group_by": col_ids.get("Status", ""),
            "card_fields": [col_ids.get("Title", ""), col_ids.get("Priority", ""), col_ids.get("Assignee", "")],
        },
        created_by=user.user_id,
    )
    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Roadmap",
        view_type="timeline",
        config={
            "start_col": col_ids.get("Start Date", ""),
            "end_col": col_ids.get("Due Date", ""),
            "color_by": col_ids.get("Status", ""),
            "group_by": col_ids.get("Type", ""),
        },
        created_by=user.user_id,
    )
    await view_repo.set_order(
        table.workspace_id,
        table.table_id,
        ["Sprint Board", "Roadmap"],
        updated_by=user.user_id,
    )
    await view_repo.set_default_view(table.workspace_id, table.table_id, "Sprint Board")

    return await _build_table_response(table, session)


@router.post("/template/crm", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_crm_template(
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    table_id = data.get("table_id", "") or data.get("table_name", "") or data.get("name", "")
    if not table_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="table_id is required")
    ws_repo = WorkspaceRepository(session)
    workspace_id = await _resolve_template_workspace(data, user, ws_repo)

    table_repo = TableRepository(session)
    table = await table_repo.create(workspace_id=workspace_id, table_id=table_id)

    columns, col_ids = _build_columns(_CRM_COLUMNS)
    view_repo = TableViewRepository(session)
    await view_repo.set_schema(table.workspace_id, table.table_id, columns, updated_by=user.user_id)
    for col in columns:
        try:
            await table_repo.create_column_index(table.table_id, col["column_id"], col["type"])
        except Exception:
            pass

    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Pipeline",
        view_type="kanban",
        config={
            "group_by": col_ids.get("Stage", ""),
            "card_fields": [col_ids.get("Title", ""), col_ids.get("Value", ""), col_ids.get("Owner", "")],
        },
        created_by=user.user_id,
    )
    await view_repo.create(
        workspace_id=table.workspace_id,
        table_id=table.table_id,
        name="Sales Dashboard",
        view_type="dashboard",
        config={
            "layout": [
                {"id": "pipeline_value", "x": 0, "y": 0, "w": 3, "h": 2},
                {"id": "by_stage", "x": 3, "y": 0, "w": 6, "h": 4},
                {"id": "by_owner", "x": 9, "y": 0, "w": 3, "h": 4},
                {"id": "won_value", "x": 0, "y": 2, "w": 3, "h": 2},
                {"id": "recent", "x": 0, "y": 4, "w": 12, "h": 4},
            ],
            "blocks": {
                "pipeline_value": {
                    "kind": "number",
                    "title": "Pipeline Value",
                    "lql": (
                        f'table("{table_id}")'
                        ' | filter((r)->{r.stage in @["lead","qualified","proposal"]})'
                        ' | aggregate(@{"value": sum(r.value)})'
                    ),
                    "field": "value",
                    "format": "$,.0f",
                },
                "by_stage": {
                    "kind": "chart",
                    "title": "Value by Stage",
                    "lql": (
                        f'table("{table_id}") | group_by((r)->{{r.stage}}) | aggregate(@{{"value": sum(r.value)}})'
                    ),
                    "echarts": {
                        "dataset": [{"$inject": "rows"}],
                        "xAxis": {"type": "category"},
                        "yAxis": {"type": "value"},
                        "series": [{"type": "bar", "encode": {"x": "dim_0", "y": "value"}}],
                    },
                },
                "by_owner": {
                    "kind": "chart",
                    "title": "Deals by Owner",
                    "lql": f'table("{table_id}") | group_by((r)->{{r.owner}}) | aggregate(count())',
                    "echarts": {
                        "dataset": [{"$inject": "rows"}],
                        "xAxis": {"type": "category"},
                        "yAxis": {"type": "value"},
                        "series": [{"type": "bar", "encode": {"x": "dim_0", "y": "count"}}],
                    },
                },
                "won_value": {
                    "kind": "number",
                    "title": "Won Value",
                    "lql": (
                        f'table("{table_id}") | filter((r)->{{r.stage=="won"}}) | aggregate(@{{"value": sum(r.value)}})'
                    ),
                    "field": "value",
                    "format": "$,.0f",
                },
                "recent": {
                    "kind": "list",
                    "title": "Recent Deals",
                    "lql": f'table("{table_id}") | limit(10)',
                    "columns": [],
                },
            },
        },
        created_by=user.user_id,
    )
    await view_repo.set_order(
        table.workspace_id,
        table.table_id,
        ["Pipeline", "Sales Dashboard"],
        updated_by=user.user_id,
    )

    return await _build_table_response(table, session)
