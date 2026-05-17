#!/usr/bin/env python3
"""E2E test: column_option_colors — option color edit propagates across views.

Topic: Editing a select-column option's color in ManageOptionsModal persists to the
DB and is reflected in both the Table view (select-cell pill) and the Kanban view
(lane header pill), including after navigation away and back.

Three pillars (developing-e2e-test):
  - Playwright UI    — open ManageOptionsModal, change color, click Save
  - BE API verify    — PATCH /tables/{tid}/columns/{cid} confirmed; GET checks new color
  - Cross-view check — Table view pill + Kanban lane header both show new color;
                       navigation away-and-back proves durability

Flow:
  setup:  login as "lattice" → create workspace → create PM table (Status col
          with todo/in_progress/done options) → add one row with Status='todo'
  step 1: Table view → open Status col menu → click "Manage Options"
          → change 'todo' color from #9ca3af → #e74c3c → Save
          → wait for PATCH; API + UI verify
  step 2: Still on Table view — check the select cell pill shows new color
  step 3: Navigate to Sprint Board (kanban) — lane header for 'todo' shows new color
  step 4: Navigate away and back — both table + kanban colors still correct
  teardown: DELETE workspace

Usage:
    docker compose exec -T test-e2e pytest tables/test_column_option_colors.py -v
    docker compose exec -T test-e2e pytest tables/test_column_option_colors.py -v --snapshot
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

NEW_COLOR = "#e74c3c"
# Browser normalizes #RRGGBB → rgb(R, G, B) in getAttribute('style')
_r, _g, _b = int(NEW_COLOR[1:3], 16), int(NEW_COLOR[3:5], 16), int(NEW_COLOR[5:7], 16)
NEW_COLOR_RGB = f"rgb({_r}, {_g}, {_b})"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_id: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_view_tabs", snapshot)
        pytest.fail(f"View tabs did not load for table {table_id}")


def test_column_option_colors(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table

    # ── API verify: find Status select column and its 'todo' choice ────────
    status_col = next(
        (c for c in columns if c.get("name") == "Status" and c.get("type") == "select"),
        None,
    )
    assert status_col, (
        f"PM template has no 'Status' select column; "
        f"got {[(c['name'], c['type']) for c in columns]}"
    )
    status_col_id = status_col["column_id"]
    choices = status_col.get("options", {}).get("choices", [])
    todo_choice = next((c for c in choices if c.get("value") == "todo"), None)
    assert todo_choice, f"Status column has no 'todo' choice; got {choices}"
    original_color = todo_choice.get("color", "")
    print(f"[ok] col='Status' ({status_col_id[:8]}…) choice[0]='todo' color={original_color!r}")

    # Verify Sprint Board kanban view exists
    kanban_views = [v for v in views if v.get("type") == "kanban"]
    assert kanban_views, (
        f"PM template has no kanban view; types={[v.get('type') for v in views]}"
    )
    print(f"[ok] kanban view found: view_id={kanban_views[0].get('view_id')}")

    # ── Add a Table view (PM template only creates kanban + timeline) ──────
    r = api("POST", f"/api/v1/tables/{table_id}/views", admin_token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code == 201, f"add Table view: {r.status_code} {r.text[:200]}"
    print("[ok] added 'Table' view to PM table")

    # ── Add row with Status='todo' ─────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
            json={"row_data": {status_col_id: "todo"}})
    assert r.status_code == 201, f"add row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] row added with Status='todo' (row_id={row_id})")

    # ── Browser session ────────────────────────────────────────────────────
    goto_table(page, ws_id, table_id, snapshot)

    # Click the "Table" view tab we added (PM template default is kanban)
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible — view may not have been created")
    page.click(table_tab)

    # Wait for table grid (thead signals the grid rendered)
    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_table_grid", snapshot)
        pytest.fail("Table grid did not render")

    snap(page, "opt_clr_01_initial_table", snapshot)

    # ── step 1: open column menu for Status ────────────────────────────────
    col_toggle = f'[data-testid="col-menu-toggle-{status_col_id}"]'
    try:
        page.wait_for_selector(col_toggle, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_col_toggle", snapshot)
        pytest.fail(f"Column menu toggle for Status ({status_col_id[:8]}…) not found — missing data-testid?")
    page.click(col_toggle)

    manage_btn = f'[data-testid="col-manage-options-{status_col_id}"]'
    try:
        page.wait_for_selector(manage_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_manage_btn", snapshot)
        pytest.fail("'Manage Options' menu item not visible — Status column not select type or testid missing")
    page.click(manage_btn)
    print("[ok] opened ManageOptionsModal for Status")

    # ── step 2: change 'todo' color ────────────────────────────────────────
    color_btn = '[data-testid="choice-color-btn-0"]'
    try:
        page.wait_for_selector(color_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_color_btn", snapshot)
        pytest.fail("choice-color-btn-0 not visible in ManageOptionsModal")
    page.click(color_btn)
    print("[ok] opened color picker for 'todo'")

    hex_input = '[data-testid="color-picker-hex"]'
    try:
        page.wait_for_selector(hex_input, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_hex_input", snapshot)
        pytest.fail("color-picker-hex input not visible")

    # Clear and type the new color
    page.fill(hex_input, NEW_COLOR)
    snap(page, "opt_clr_02_color_picker_filled", snapshot)

    page.click('[data-testid="color-picker-apply"]')
    print(f"[ok] applied new color {NEW_COLOR!r}")

    # ── step 3: save + wait for PATCH ──────────────────────────────────────
    save_btn = '[data-testid="manage-options-save-btn"]'
    try:
        page.wait_for_selector(save_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_save_btn", snapshot)
        pytest.fail("manage-options-save-btn not found in ManageOptionsModal")

    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/columns/{status_col_id}" in resp.url
            and resp.request.method == "PATCH"
            and resp.ok
        ),
        timeout=10000,
    ):
        page.click(save_btn)
    print("[ok] Save clicked; PATCH confirmed")

    snap(page, "opt_clr_03_after_save", snapshot)

    # ── API pillar: verify new color persisted in DB ───────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}", admin_token)
    assert r.status_code == 200, f"GET table after save: {r.status_code} {r.text[:200]}"
    refreshed_cols = r.json()["columns"]
    updated_status = next(
        (c for c in refreshed_cols if c["column_id"] == status_col_id), None
    )
    assert updated_status, "Status column missing from refreshed schema"
    updated_choices = updated_status.get("options", {}).get("choices", [])
    updated_todo = next((c for c in updated_choices if c.get("value") == "todo"), None)
    assert updated_todo, f"'todo' choice missing after save; got {updated_choices}"
    db_color = updated_todo.get("color", "")
    assert db_color.lower() == NEW_COLOR.lower(), (
        f"API: 'todo' color={db_color!r}, expected {NEW_COLOR!r}"
    )
    print(f"[ok] API: 'todo' color={db_color!r} persisted in DB")

    # ── UI pillar: table view — select cell pill shows new color ───────────
    # After PATCH, refreshTable fires GET /tables/{id} to update $columns.
    # Wait for the reactive re-render: cell style must contain the new color.
    cell_sel = f'[data-testid="select-cell-{row_id}-{status_col_id}"]'
    try:
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector(
                    '[data-testid="select-cell-{row_id}-{status_col_id}"]'
                );
                return el && (el.getAttribute('style') || '').includes('{NEW_COLOR_RGB}');
            }}""",
            timeout=10000,
        )
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_cell_color", snapshot)
        cell_style_now = page.locator(cell_sel).get_attribute("style") or "(not found)"
        pytest.fail(
            f"Table view: select-cell style did not update to {NEW_COLOR!r} "
            f"(rgb={NEW_COLOR_RGB}) after refreshTable; got style={cell_style_now!r}"
        )

    cell_style = page.locator(cell_sel).get_attribute("style") or ""
    print(f"[ok] Table view: select-cell style contains {NEW_COLOR_RGB!r}")
    snap(page, "opt_clr_04_table_cell_color", snapshot)

    # ── step 4: navigate to Sprint Board (kanban) ──────────────────────────
    sprint_tab = '[data-testid="view-tab-Sprint Board"]'
    try:
        page.wait_for_selector(sprint_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_sprint_tab", snapshot)
        pytest.fail("Sprint Board tab not visible")
    page.click(sprint_tab)
    print("[ok] clicked Sprint Board kanban tab")

    lane_sel = '[data-testid="kanban-lane-header-todo"]'
    try:
        page.wait_for_selector(lane_sel, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_lane_header", snapshot)
        pytest.fail("kanban-lane-header-todo not visible — lane may not have rendered")

    lane_style = page.locator(lane_sel).get_attribute("style") or ""
    assert NEW_COLOR_RGB in lane_style, (
        f"Kanban: lane header style does not contain {NEW_COLOR_RGB!r}; "
        f"got style={lane_style!r}"
    )
    print(f"[ok] Kanban: lane header 'todo' style contains {NEW_COLOR_RGB!r}")
    snap(page, "opt_clr_05_kanban_lane_color", snapshot)

    # ── step 5: navigate away and back; verify both views ──────────────────
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id, snapshot)

    # Re-click the Table tab after navigation back
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_table_after_nav", snapshot)
        pytest.fail("Table grid did not render after navigation back")

    cell_style2 = page.locator(cell_sel).get_attribute("style") or ""
    assert NEW_COLOR_RGB in cell_style2, (
        f"Table view after nav: select-cell style does not contain {NEW_COLOR_RGB!r}; "
        f"got style={cell_style2!r}"
    )
    print(f"[ok] Table view (after nav): select-cell style still contains {NEW_COLOR_RGB!r}")

    page.click(sprint_tab)
    try:
        page.wait_for_selector(lane_sel, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "opt_clr_FAIL_no_lane_after_nav", snapshot)
        pytest.fail("kanban-lane-header-todo not visible after navigation back")

    lane_style2 = page.locator(lane_sel).get_attribute("style") or ""
    assert NEW_COLOR_RGB in lane_style2, (
        f"Kanban (after nav): lane header style does not contain {NEW_COLOR_RGB!r}; "
        f"got style={lane_style2!r}"
    )
    print(f"[ok] Kanban (after nav): lane header 'todo' style still contains {NEW_COLOR_RGB!r}")
    snap(page, "opt_clr_06_kanban_after_nav", snapshot)

    print("\n=== PASSED — test_column_option_colors ===")
