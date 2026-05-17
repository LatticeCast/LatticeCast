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
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_col_resize.py [--snapshot]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time())
WORKSPACE_NAME = f"colresize-{_TS}"
TABLE_ID = f"col-resize-{_TS}"
COL_NAME = "Title"
VIEW_NAME = "Resize View"
DRAG_DELTA = 100  # px to drag right
DEFAULT_WIDTH = 150  # FE fallback when no width stored
TOLERANCE = 5  # px tolerance for float rounding


def fatal(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def login(user_name: str) -> str:
    r = requests.post(
        f"{BASE}/api/v1/login/password",
        json={"user_name": user_name, "password": ""},
        timeout=10,
    )
    if r.status_code != 200:
        fatal(f"login {user_name!r}: {r.status_code} {r.text[:200]}")
    token = r.json()["access_token"]
    print(f"[ok] login {user_name!r}")
    return token


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def get_view_config(token: str, table_id: str, view_id: int) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}/views/{view_id}", token)
    if r.status_code != 200:
        fatal(f"GET view {view_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def wait_table_page(page, ws_name: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        fatal(f"Table page did not finish loading for {table_id!r}")


def get_th_width_px(page, col_id: str) -> int:
    """Read the rendered pixel width of the column header <th>."""
    th = page.locator(f'[data-testid="col-header-{col_id}"]')
    try:
        th.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        fatal(f"col-header-{col_id} not visible")
    box = th.bounding_box()
    if box is None:
        fatal(f"col-header-{col_id} has no bounding box")
    return round(box["width"])


def drag_resize_handle(page, col_id: str, delta_px: int) -> None:
    """Drag the resize handle of a column right by delta_px pixels."""
    handle = page.locator(f'[data-testid="col-resize-handle-{col_id}"]')
    try:
        handle.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        fatal(f"col-resize-handle-{col_id} not visible")
    box = handle.bounding_box()
    if box is None:
        fatal(f"col-resize-handle-{col_id} has no bounding box")
    # Centre of the handle
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + delta_px, cy, steps=10)
    page.mouse.up()


def main(snapshot: bool = False) -> None:
    token = login(ADMIN_USER)

    # ── Setup: workspace ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: text column ───────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
            json={"name": COL_NAME, "type": "text"})
    if r.status_code not in (200, 201):
        fatal(f"create column: {r.status_code} {r.text[:200]}")
    schema = r.json()
    col = next((c for c in schema.get("columns", []) if c["name"] == COL_NAME), None)
    if not col:
        fatal(f"column {COL_NAME!r} not found in schema: {schema.get('columns')}")
    col_id = col["column_id"]
    print(f"[setup] column {COL_NAME!r} id={col_id}")

    # ── Setup: table view ────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": VIEW_NAME, "type": "table"})
    if r.status_code not in (200, 201):
        fatal(f"create view: {r.status_code} {r.text[:200]}")
    view_schema = r.json()
    view = next((v for v in view_schema.get("views", []) if v["name"] == VIEW_NAME), None)
    if not view:
        fatal(f"view {VIEW_NAME!r} not found in schema: {view_schema.get('views')}")
    view_id = view["view_id"]
    print(f"[setup] view {VIEW_NAME!r} id={view_id}")

    login_info = (
        '{"provider":"none",'
        f'"accessToken":"{token}",'
        f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
        '"role":"admin"}'
    )

    with sync_playwright() as pw:
        browser = pw.chromium.connect(WS_URL)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(f"localStorage.setItem('loginInfo', {repr(login_info)});")
        page = ctx.new_page()

        # ── Step 1: navigate and activate the view ────────────────────────────
        wait_table_page(page, ws_name, TABLE_ID)

        # Click the view tab to activate Resize View
        tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible")
        tab.click()
        # Wait until the view is active (the table view renders the col header)
        try:
            page.wait_for_selector(f'[data-testid="col-header-{col_id}"]', timeout=8000)
        except PlaywrightTimeout:
            fatal(f"col-header-{col_id} not visible after switching to view")

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

        if not resp_info.value.ok:
            fatal(f"PUT view returned {resp_info.value.status}: {resp_info.value.text()[:200]}")
        print(f"[ok] PUT view responded {resp_info.value.status}")

        snap(page, "cr_02_after_resize", snapshot)

        # ── Step 3: verify UI width after resize ─────────────────────────────
        actual_ui_width = get_th_width_px(page, col_id)
        if abs(actual_ui_width - expected_width) > TOLERANCE:
            fatal(
                f"UI width after resize: expected ~{expected_width}px, got {actual_ui_width}px"
            )
        print(f"[ok] UI: col width after resize = {actual_ui_width}px (~{expected_width})")

        # ── Step 4: verify DB via API ─────────────────────────────────────────
        view_cfg = get_view_config(token, TABLE_ID, view_id)
        db_widths = view_cfg.get("config", {}).get("widths", {})
        db_width = db_widths.get(col_id)
        if db_width is None:
            fatal(f"API: config.widths missing col_id={col_id}; got widths={db_widths}")
        if abs(int(db_width) - expected_width) > TOLERANCE:
            fatal(f"API: config.widths[{col_id}]={db_width}, expected ~{expected_width}")
        print(f"[ok] API: config.widths[{col_id}]={db_width} (~{expected_width})")

        # ── Step 5: navigate away (tables list) and back ──────────────────────
        page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
        snap(page, "cr_03_away", snapshot)

        wait_table_page(page, ws_name, TABLE_ID)
        # Re-activate Resize View (it may default to Schema on fresh load)
        tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab2.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible after reload")
        tab2.click()
        try:
            page.wait_for_selector(f'[data-testid="col-header-{col_id}"]', timeout=8000)
        except PlaywrightTimeout:
            fatal(f"col-header-{col_id} not visible after reload + tab click")

        snap(page, "cr_04_after_reload", snapshot)

        # ── Step 6: verify persistence in UI ─────────────────────────────────
        persisted_ui_width = get_th_width_px(page, col_id)
        if abs(persisted_ui_width - expected_width) > TOLERANCE:
            fatal(
                f"UI width after reload: expected ~{expected_width}px (persisted), "
                f"got {persisted_ui_width}px — width was NOT persisted"
            )
        print(f"[ok] UI: col width persisted after reload = {persisted_ui_width}px")

        # ── Step 7: verify DB again (no regression) ───────────────────────────
        view_cfg2 = get_view_config(token, TABLE_ID, view_id)
        db_widths2 = view_cfg2.get("config", {}).get("widths", {})
        db_width2 = db_widths2.get(col_id)
        if db_width2 is None:
            fatal(f"API after reload: config.widths missing col_id={col_id}; got widths={db_widths2}")
        if abs(int(db_width2) - expected_width) > TOLERANCE:
            fatal(f"API after reload: config.widths[{col_id}]={db_width2}, expected ~{expected_width}")
        print(f"[ok] API after reload: config.widths[{col_id}]={db_width2}")

        snap(page, "cr_05_final", snapshot)
        browser.close()

    # ── Teardown ──────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_view_table_col_resize ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true", help="Capture screenshots at each step")
    args = parser.parse_args()
    main(snapshot=args.snapshot)
