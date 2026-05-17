"""E2E test: column width persists across navigation in the Table view.

Scenario:
  1. Create a workspace + table + text column + table view.
  2. Navigate to the table page; wait for it to load.
  3. Read the initial column width from the UI (default 150 px).
  4. Drag the resize handle 100 px to the right.
  5. Wait for the PUT /views/{view_id} API response.
  6. Assert DB: view config.widths[col_id] ≈ 250.
  7. Assert UI: <th data-testid="col-header-{col_id}"> style width ≈ 250 px.
  8. Navigate away (tables list) then back.
  9. Assert UI: column width still ≈ 250 px (persisted on reload).
 10. Assert DB: view config.widths[col_id] still ≈ 250 (no regression).

Two-container architecture (developing-e2e-test):
  - Runs in test-e2e container (no Chromium).
  - Playwright connects to browser service via BROWSER_WS.
  - API checks hit BE through BASE_URL.

Usage:
    docker compose exec test-e2e pytest tables/test_col_resize.py -v
    docker compose exec test-e2e pytest tables/test_col_resize.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

ADMIN_USER = "lattice"
COL_NAME = "Title"
VIEW_NAME = "Resize View"
DRAG_DELTA = 100  # px to drag right
DEFAULT_WIDTH = 150  # FE fallback when no width stored
TOLERANCE = 5  # px tolerance for float rounding


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def get_view_config(token: str, table_id: str, view_id: int) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}/views/{view_id}", token)
    assert r.status_code == 200, f"GET view {view_id}: {r.status_code} {r.text[:200]}"
    return r.json()


def wait_table_page(page, ws_name: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        snap(page, "cr_FAIL_table_not_loaded", snapshot)
        pytest.fail(f"Table page did not finish loading for {table_id!r}")


def get_th_width_px(page, col_id: str) -> int:
    """Read the rendered pixel width of the column header <th>."""
    th = page.locator(f'[data-testid="col-header-{col_id}"]')
    try:
        th.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        pytest.fail(f"col-header-{col_id} not visible")
    box = th.bounding_box()
    assert box is not None, f"col-header-{col_id} has no bounding box"
    return round(box["width"])


def drag_resize_handle(page, col_id: str, delta_px: int) -> None:
    """Drag the resize handle of a column right by delta_px pixels."""
    handle = page.locator(f'[data-testid="col-resize-handle-{col_id}"]')
    try:
        handle.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        pytest.fail(f"col-resize-handle-{col_id} not visible")
    box = handle.bounding_box()
    assert box is not None, f"col-resize-handle-{col_id} has no bounding box"
    # Centre of the handle
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + delta_px, cy, steps=10)
    page.mouse.up()


def test_col_resize(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace
    _ts = int(time.time()) % 100000
    table_id = f"col-resize-{_ts}"

    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[setup] table {table_id!r}")

    # ── Setup: text column ───────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token,
            json={"name": COL_NAME, "type": "text"})
    assert r.status_code in (200, 201), f"create column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    col = next((c for c in schema.get("columns", []) if c["name"] == COL_NAME), None)
    assert col is not None, f"column {COL_NAME!r} not found in schema: {schema.get('columns')}"
    col_id = col["column_id"]
    print(f"[setup] column {COL_NAME!r} id={col_id}")

    # ── Setup: table view ────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": VIEW_NAME, "type": "table"})
    assert r.status_code in (200, 201), f"create view: {r.status_code} {r.text[:200]}"
    view_schema = r.json()
    view = next((v for v in view_schema.get("views", []) if v["name"] == VIEW_NAME), None)
    assert view is not None, f"view {VIEW_NAME!r} not found in schema: {view_schema.get('views')}"
    view_id = view["view_id"]
    print(f"[setup] view {VIEW_NAME!r} id={view_id}")

    # ── Step 1: navigate and activate the view ────────────────────────────
    wait_table_page(page, ws_name, table_id, snapshot)

    # Click the view tab to activate Resize View
    tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
    try:
        tab.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "cr_FAIL_tab_not_visible", snapshot)
        pytest.fail(f"Tab {VIEW_NAME!r} not visible")
    tab.click()
    # Wait until the view is active (the table view renders the col header)
    try:
        page.wait_for_selector(f'[data-testid="col-header-{col_id}"]', timeout=8000)
    except PlaywrightTimeout:
        snap(page, "cr_FAIL_col_header_not_visible", snapshot)
        pytest.fail(f"col-header-{col_id} not visible after switching to view")

    snap(page, "cr_01_initial", snapshot)
    initial_width = get_th_width_px(page, col_id)
    print(f"[ok] initial col width in UI: {initial_width}px (expected ~{DEFAULT_WIDTH})")

    # ── Step 2: drag resize handle +100 px ───────────────────────────────
    expected_width = initial_width + DRAG_DELTA
    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                  and r.request.method == "PUT"
    ) as resp_info:
        drag_resize_handle(page, col_id, DRAG_DELTA)

    assert resp_info.value.ok, (
        f"PUT view returned {resp_info.value.status}: {resp_info.value.text()[:200]}"
    )
    print(f"[ok] PUT view responded {resp_info.value.status}")

    snap(page, "cr_02_after_resize", snapshot)

    # ── Step 3: verify UI width after resize ─────────────────────────────
    actual_ui_width = get_th_width_px(page, col_id)
    assert abs(actual_ui_width - expected_width) <= TOLERANCE, (
        f"UI width after resize: expected ~{expected_width}px, got {actual_ui_width}px"
    )
    print(f"[ok] UI: col width after resize = {actual_ui_width}px (~{expected_width})")

    # ── Step 4: verify DB via API ─────────────────────────────────────────
    view_cfg = get_view_config(token, table_id, view_id)
    db_widths = view_cfg.get("config", {}).get("widths", {})
    db_width = db_widths.get(col_id)
    assert db_width is not None, (
        f"API: config.widths missing col_id={col_id}; got widths={db_widths}"
    )
    assert abs(int(db_width) - expected_width) <= TOLERANCE, (
        f"API: config.widths[{col_id}]={db_width}, expected ~{expected_width}"
    )
    print(f"[ok] API: config.widths[{col_id}]={db_width} (~{expected_width})")

    # ── Step 5: navigate away (tables list) and back ──────────────────────
    page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
    snap(page, "cr_03_away", snapshot)

    wait_table_page(page, ws_name, table_id, snapshot)
    # Re-activate Resize View (it may default to Schema on fresh load)
    tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
    try:
        tab2.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "cr_FAIL_tab_not_visible_after_reload", snapshot)
        pytest.fail(f"Tab {VIEW_NAME!r} not visible after reload")
    tab2.click()
    try:
        page.wait_for_selector(f'[data-testid="col-header-{col_id}"]', timeout=8000)
    except PlaywrightTimeout:
        snap(page, "cr_FAIL_col_header_after_reload", snapshot)
        pytest.fail(f"col-header-{col_id} not visible after reload + tab click")

    snap(page, "cr_04_after_reload", snapshot)

    # ── Step 6: verify persistence in UI ─────────────────────────────────
    persisted_ui_width = get_th_width_px(page, col_id)
    assert abs(persisted_ui_width - expected_width) <= TOLERANCE, (
        f"UI width after reload: expected ~{expected_width}px (persisted), "
        f"got {persisted_ui_width}px — width was NOT persisted"
    )
    print(f"[ok] UI: col width persisted after reload = {persisted_ui_width}px")

    # ── Step 7: verify DB again (no regression) ───────────────────────────
    view_cfg2 = get_view_config(token, table_id, view_id)
    db_widths2 = view_cfg2.get("config", {}).get("widths", {})
    db_width2 = db_widths2.get(col_id)
    assert db_width2 is not None, (
        f"API after reload: config.widths missing col_id={col_id}; got widths={db_widths2}"
    )
    assert abs(int(db_width2) - expected_width) <= TOLERANCE, (
        f"API after reload: config.widths[{col_id}]={db_width2}, expected ~{expected_width}"
    )
    print(f"[ok] API after reload: config.widths[{col_id}]={db_width2}")

    snap(page, "cr_05_final", snapshot)

    print("\n=== PASSED — test_col_resize ===")
