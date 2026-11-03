"""All table views and exports include rows beyond the first API page."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from e2e_base import BASE, api


def test_table_all_rows(authed_page, admin_token, pm_table, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table
    column_ids = {column["name"]: column["column_id"] for column in columns}
    assert {"Title", "Status"} <= column_ids.keys()
    kanban = next(view for view in views if view["type"] == "kanban")
    timeline = next(view for view in views if view["type"] == "timeline")
    start_col = timeline["config"]["start_col"]
    end_col = timeline["config"].get("end_col")

    row_ids = []
    for index in range(1, 102):
        data = {
            column_ids["Title"]: f"full-row-{index:03d}",
            column_ids["Status"]: "todo",
            start_col: "2026-10-01",
        }
        if end_col:
            data[end_col] = "2026-10-31"
        response = api(
            "POST", f"/api/v1/tables/{table_id}/rows", admin_token,
            json={"row_data": data},
        )
        assert response.status_code == 201, response.text[:200]
        row_ids.append(response.json()["row_id"])

    response = api("GET", f"/api/v1/tables/{table_id}/rows?limit=200&sort=asc", admin_token)
    assert response.status_code == 200, response.text[:200]
    persisted = response.json()
    assert len(persisted) == 101
    assert [row["row_id"] for row in persisted] == row_ids
    last_id = row_ids[-1]
    assert persisted[-1]["row_data"][column_ids["Title"]] == "full-row-101"

    ui_base = os.environ.get("E2E_FRONTEND_URL", BASE)
    page.goto(f"{ui_base}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    page.locator('[data-table-loaded="true"]').wait_for(state="attached")
    page.get_by_test_id("view-tab-Schema").click()
    last_grid_row = page.get_by_test_id(f"grid-row-{last_id}")
    last_grid_row.scroll_into_view_if_needed()
    assert page.locator('[data-testid^="grid-row-"]').count() == 101
    if snapshot:
        page.screenshot(path="/output/table_all_rows_grid.png", full_page=True)

    page.get_by_test_id(f"view-tab-{kanban['name']}").click()
    last_card = page.get_by_test_id(f"kanban-card-{last_id}-btn")
    last_card.scroll_into_view_if_needed()
    assert page.locator('[data-testid^="kanban-card-"][draggable="true"]').count() == 101
    if snapshot:
        page.screenshot(path="/output/table_all_rows_kanban.png", full_page=True)

    page.get_by_test_id(f"view-tab-{timeline['name']}").click()
    last_bar = page.get_by_test_id(f"timeline-row-bar-{last_id}")
    last_bar.scroll_into_view_if_needed()
    assert page.locator('[data-testid^="timeline-row-bar-"]').count() == 101
    if snapshot:
        page.screenshot(path="/output/table_all_rows_timeline.png", full_page=True)

    page.get_by_test_id("view-tab-Schema").click()
    output = Path("/output")
    for label, extension in (("Export CSV", "csv"), ("Export JSON", "json")):
        page.get_by_test_id("toolbar-export-btn").click()
        with page.expect_download() as download_info:
            page.get_by_role("menuitem", name=label).click()
        destination = output / f"table_all_rows_{table_id}.{extension}"
        download_info.value.save_as(destination)
        assert download_info.value.failure() is None
        if extension == "csv":
            with destination.open(newline="") as file:
                exported = list(csv.DictReader(file))
        else:
            exported = json.loads(destination.read_text())
        assert len(exported) == 101
        # Export reuses the same fetchAllRows() the grid loads from, which
        # defaults to newest-first (reverse row_id order).
        assert exported[0]["Title"] == "full-row-101"
        assert exported[-1]["Title"] == "full-row-001"
