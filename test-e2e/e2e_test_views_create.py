"""E2E test: + Add View of each type creates the correct tab and persists.

Covers all three user-creatable view types (table, kanban, timeline) by
clicking the "Add view" panel in the UI, then verifying:
  1. New tab appears in the ViewSwitcher immediately.
  2. GET /tables/{table_id} returns the new view in the API response.
  3. A second view of the same type gets an auto-numbered name.
  4. All views survive a navigate-away + navigate-back round-trip.

Two-container architecture (developing-e2e-test):
  - Runs in test-e2e container (no Chromium).
  - Playwright connects to browser service via BROWSER_WS.
  - API checks hit BE through BASE_URL.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_views_create.py [--snapshot]
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
WORKSPACE_NAME = f"view-create-{_TS}"
TABLE_ID = f"views-create-{_TS}"


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


def get_views(token: str, table_id: str) -> list[dict]:
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    if r.status_code != 200:
        fatal(f"GET /tables/{table_id}: {r.status_code} {r.text[:200]}")
    return r.json().get("views", [])


def assert_api_has_view(token: str, table_id: str, name: str, vtype: str) -> dict:
    views = get_views(token, table_id)
    match = next((v for v in views if v["name"] == name and v["type"] == vtype), None)
    if match is None:
        names = [(v["name"], v["type"]) for v in views]
        fatal(f"API: no view name={name!r} type={vtype!r} in {names}")
    print(f"[ok] API: view name={name!r} type={vtype!r} view_id={match['view_id']}")
    return match


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


def click_add_view_type(page, vtype: str) -> None:
    """Open the Add view panel and click the given view type button."""
    add_btn = page.locator('[data-testid="view-switcher-add-btn"]')
    add_btn.wait_for(state="visible", timeout=5000)
    add_btn.click()
    type_btn = page.locator(f'[data-testid="view-type-{vtype}-btn"]')
    type_btn.wait_for(state="visible", timeout=3000)
    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views" in r.url and r.request.method == "POST"
    ) as resp_info:
        type_btn.click()
    assert resp_info.value.ok, f"POST /views for type={vtype!r} returned {resp_info.value.status}"


def assert_tab_visible(page, tab_name: str) -> None:
    try:
        page.locator(f'[data-testid="view-tab-{tab_name}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        fatal(f"view tab {tab_name!r} not visible after creation")
    print(f"[ok] UI: tab {tab_name!r} visible")


def main(snapshot: bool = False) -> None:
    token = login(ADMIN_USER)

    # ── Setup: workspace ───────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[ok] CREATE workspace {ws_name!r} → {ws_uuid}")

    # ── Setup: blank table (no views) ──────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    print(f"[ok] CREATE table {TABLE_ID!r}")

    # ── Playwright session ─────────────────────────────────────────────────────
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

        wait_table_page(page, ws_name, TABLE_ID)
        print("[ok] navigated to table page")
        snap(page, "vc_01_initial", snapshot)

        # ── Step 1: Add a Table view ───────────────────────────────────────────
        # The implicit "Schema" view (view_id=0) is type=table, so the first
        # user-created table view is auto-named "Table 2" (existing count = 1).
        click_add_view_type(page, "table")
        TABLE_VIEW_NAME = "Table 2"
        assert_tab_visible(page, TABLE_VIEW_NAME)
        snap(page, "vc_02_table_created", snapshot)
        table_view = assert_api_has_view(token, TABLE_ID, TABLE_VIEW_NAME, "table")

        # ── Step 2: Add a Kanban view ──────────────────────────────────────────
        click_add_view_type(page, "kanban")
        KANBAN_VIEW_NAME = "Kanban"
        assert_tab_visible(page, KANBAN_VIEW_NAME)
        snap(page, "vc_03_kanban_created", snapshot)
        assert_api_has_view(token, TABLE_ID, KANBAN_VIEW_NAME, "kanban")

        # ── Step 3: Add a Timeline view ────────────────────────────────────────
        click_add_view_type(page, "timeline")
        TIMELINE_VIEW_NAME = "Timeline"
        assert_tab_visible(page, TIMELINE_VIEW_NAME)
        snap(page, "vc_04_timeline_created", snapshot)
        assert_api_has_view(token, TABLE_ID, TIMELINE_VIEW_NAME, "timeline")

        # ── Step 4: Second Kanban → auto-numbered "Kanban 2" ───────────────────
        click_add_view_type(page, "kanban")
        KANBAN2_VIEW_NAME = "Kanban 2"
        assert_tab_visible(page, KANBAN2_VIEW_NAME)
        snap(page, "vc_05_kanban2_created", snapshot)
        assert_api_has_view(token, TABLE_ID, KANBAN2_VIEW_NAME, "kanban")

        # ── Step 5: navigate away + back → all views persist ──────────────────
        page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded", timeout=15000)
        wait_table_page(page, ws_name, TABLE_ID)
        print("[ok] navigated back to table page")
        snap(page, "vc_06_after_nav", snapshot)

        for tab_name in [TABLE_VIEW_NAME, KANBAN_VIEW_NAME, TIMELINE_VIEW_NAME, KANBAN2_VIEW_NAME]:
            try:
                page.locator(f'[data-testid="view-tab-{tab_name}"]').wait_for(
                    state="visible", timeout=8000
                )
            except PlaywrightTimeout:
                fatal(f"view tab {tab_name!r} not visible after navigation")
            print(f"[ok] tab {tab_name!r} persists after navigation")

        browser.close()

    # ── Teardown ────────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_views_create ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true", help="Capture screenshots at each step")
    args = parser.parse_args()
    main(snapshot=args.snapshot)
