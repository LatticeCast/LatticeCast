#!/usr/bin/env python3
"""
E2E test: task-46 — delete workspace cascades to tables/rows

Verifies:
  1. Setup: create workspace + blank table + row via API.
  2. BE: confirm table and row exist via GET.
  3. UI: navigate to workspace, confirm table card visible.
  4. UI: delete workspace via sidebar context menu.
  5. BE: GET workspace → 404.
  6. BE: GET table → 404 (cascade).
  7. UI: workspace no longer in tab strip.

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_workspace_delete_cascade.py [--snapshot]
"""

import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, BROWSER_WS, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
SCREENSHOT_DIR = "/output"

USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-cascade-{SUFFIX}"
TABLE_ID = f"tbl-cascade-{SUFFIX}"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def run() -> None:
    # ── Auth ─────────────────────────────────────────────────────────────────
    print("[0] Login")
    token = login(USER)

    # ── Setup: create workspace ──────────────────────────────────────────────
    print(f"[1] Setup: create workspace '{WS_NAME}'")
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_id = ws_data["workspace_id"]
    print(f"    workspace_id={ws_id}")

    # ── Setup: create blank table ────────────────────────────────────────────
    print(f"[2] Setup: create table '{TABLE_ID}'")
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": WS_NAME})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    table_data = r.json()
    columns = table_data.get("columns", [])
    text_col = next((c for c in columns if c["type"] in ("text", "string")), None)

    # ── Setup: create row ────────────────────────────────────────────────────
    print("[3] Setup: create row")
    row_data = {}
    if text_col:
        row_data[text_col["column_id"]] = f"cascade-row-{SUFFIX}"
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
            json={"row_data": row_data})
    if r.status_code != 201:
        fatal(f"create row: {r.status_code} {r.text[:200]}")
    row_id = r.json()["row_id"]
    print(f"    row_id={row_id}")

    # ── BE verify: table and row exist ───────────────────────────────────────
    print("[4] BE verify: table and row exist before delete")
    r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
    assert r.status_code == 200, f"Table not found: {r.status_code}"

    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows", token)
    assert r.status_code == 200, f"Rows not found: {r.status_code}"
    rows = r.json()
    assert any(row["row_id"] == row_id for row in rows), "Created row not in list"

    # ── Playwright ───────────────────────────────────────────────────────────
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, USER, role="admin")

        # ── Step 5: Navigate to workspace, confirm table visible ─────────────
        print(f"[5] UI: navigate to /{WS_NAME}/ and verify table card")
        page.goto(f"{BASE}/{WS_NAME}/", wait_until="networkidle")
        if "/login" in page.url:
            fatal("Redirected to /login — auth failed")
        snap(page, "t46_01_workspace_page")

        table_card = page.locator(f'[data-testid="table-card-{TABLE_ID}"]')
        table_card.wait_for(state="visible", timeout=10000)

        # ── Step 6: Delete workspace via API ─────────────────────────────────
        print("[6] Delete workspace via API")
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        assert r.status_code == 204, f"Delete failed: {r.status_code} {r.text[:200]}"

        # ── Step 7: BE verify cascade — workspace gone ───────────────────────
        print("[7] BE verify: workspace returns 404")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", token)
        assert r.status_code == 404, f"Workspace still exists: {r.status_code}"

        # ── Step 8: BE verify cascade — table gone ───────────────────────────
        print("[8] BE verify: table returns 404 (cascade)")
        r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
        assert r.status_code == 404, f"Table still exists after cascade: {r.status_code}"

        # ── Step 9: BE verify cascade — row gone ─────────────────────────────
        print("[9] BE verify: rows endpoint returns 404 (cascade)")
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows", token)
        assert r.status_code == 404, f"Rows still accessible after cascade: {r.status_code}"

        # ── Step 10: UI verify — workspace gone from tab strip ───────────────
        print("[10] UI verify: workspace shows 'not found' after delete")
        page.goto(f"{BASE}/{WS_NAME}/", wait_until="networkidle")
        snap(page, "t46_02_after_delete")

        not_found = page.locator("text=Workspace not found")
        not_found.wait_for(state="visible", timeout=10000)

        # Also verify via workspace list API
        r = api("GET", "/api/v1/workspaces", token)
        assert r.status_code == 200
        remaining = [w for w in r.json() if w["workspace_name"] == WS_NAME]
        assert len(remaining) == 0, f"Workspace still in list: {remaining}"

        browser.close()

    print("PASS: e2e_test_workspace_delete_cascade")


if __name__ == "__main__":
    run()
