"""E2E test: view rename propagates everywhere.

Covers two view types (table + kanban) — renames each via UI inline input,
then verifies:
  1. UI tab label updates immediately.
  2. API (GET /tables/{table_id}) returns new name.
  3. Navigate away and back → new name persists.

Two-container architecture (developing-e2e-test v0.8.0):
  - Runs in test-e2e container (no Chromium).
  - Playwright connects to browser service via BROWSER_WS.
  - API checks hit BE through BASE_URL.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_views_rename.py [--snapshot]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time())
WORKSPACE_NAME = f"view-rename-{_TS}"
TABLE_ID = "views-rename"

RENAMED_TABLE_VIEW = "Renamed Table"
RENAMED_KANBAN_VIEW = "Renamed Kanban"


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
    return r.json()["access_token"]


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


def assert_api_view_name(token: str, table_id: str, view_id: int, expected: str) -> None:
    views = get_views(token, table_id)
    match = next((v for v in views if v["view_id"] == view_id), None)
    if match is None:
        fatal(f"view_id={view_id} not found in GET /tables/{table_id}")
    got = match.get("name")
    if got != expected:
        fatal(f"API view name for view_id={view_id}: got {got!r}, want {expected!r}")


def rename_view_via_ui(page, old_name: str, new_name: str) -> None:
    """Hover view tab to reveal rename button, click it, fill new name, Enter."""
    tab = page.locator(f'[data-testid="view-tab-{old_name}"]')
    tab.wait_for(state="visible", timeout=5000)
    tab.hover()
    rename_btn = page.locator(f'[data-testid="view-tab-rename-{old_name}"]')
    rename_btn.wait_for(state="visible", timeout=3000)
    rename_btn.click()
    rename_input = page.locator(f'[data-testid="view-tab-rename-input-{old_name}"]')
    rename_input.wait_for(state="visible", timeout=3000)
    rename_input.fill(new_name)
    rename_input.press("Enter")
    page.locator(f'[data-testid="view-tab-{new_name}"]').wait_for(state="visible", timeout=5000)


def main(snapshot: bool = False) -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: workspace + table ───────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] CREATE workspace {WORKSPACE_NAME!r} → {ws_id}")

    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_id})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    table = r.json()
    print(f"[ok] CREATE table {TABLE_ID!r}")

    views = table.get("views", [])
    if not views:
        fatal("blank table returned no views")
    table_view = next((v for v in views if v.get("type") == "table"), views[0])
    table_view_id = table_view["view_id"]
    original_table_name = table_view["name"]
    print(f"[ok] initial table-type view id={table_view_id} name={original_table_name!r}")

    # Add a kanban view so we cover a second view type
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": "Kanban View", "type": "kanban"})
    if r.status_code not in (200, 201):
        fatal(f"create kanban view: {r.status_code} {r.text[:200]}")
    all_views = get_views(token, TABLE_ID)
    kanban_view = next((v for v in all_views if v.get("type") == "kanban"), None)
    if kanban_view is None:
        fatal(f"kanban view not found after creation; views={all_views}")
    kanban_view_id = kanban_view["view_id"]
    original_kanban_name = kanban_view["name"]
    print(f"[ok] CREATE kanban view id={kanban_view_id} name={original_kanban_name!r}")

    # ── Playwright session ──────────────────────────────────────────────────
    login_info = (
        '{"provider":"none",'
        f'"accessToken":"{token}",'
        f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
        '"role":"admin"}'
    )

    with sync_playwright() as pw:
        browser = pw.chromium.connect(WS_URL)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(BASE, wait_until="domcontentloaded")
        page.evaluate("(info) => localStorage.setItem('loginInfo', info)", login_info)
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
        page.wait_for_timeout(2000)
        print("[ok] navigated to table page")

        if snapshot:
            page.screenshot(path="/output/views_rename_01_initial.png", full_page=True)

        # ── Step 1: rename table-type view via UI ──────────────────────────
        rename_view_via_ui(page, original_table_name, RENAMED_TABLE_VIEW)
        print(f"[ok] UI: renamed table view → {RENAMED_TABLE_VIEW!r}")

        if snapshot:
            page.screenshot(path="/output/views_rename_02_table_renamed.png", full_page=True)

        # API verify: BE returned updated name
        assert_api_view_name(token, TABLE_ID, table_view_id, RENAMED_TABLE_VIEW)
        print(f"[ok] API: table view name = {RENAMED_TABLE_VIEW!r}")

        # ── Step 2: navigate away + back → table rename persists ───────────
        page.goto(BASE, wait_until="domcontentloaded")
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
        page.locator(f'[data-testid="view-tab-{RENAMED_TABLE_VIEW}"]').wait_for(
            state="visible", timeout=8000
        )
        print(f"[ok] table view name {RENAMED_TABLE_VIEW!r} persists after navigation")

        if snapshot:
            page.screenshot(path="/output/views_rename_03_table_persists.png", full_page=True)

        # ── Step 3: rename kanban view via UI ──────────────────────────────
        rename_view_via_ui(page, original_kanban_name, RENAMED_KANBAN_VIEW)
        print(f"[ok] UI: renamed kanban view → {RENAMED_KANBAN_VIEW!r}")

        if snapshot:
            page.screenshot(path="/output/views_rename_04_kanban_renamed.png", full_page=True)

        # API verify
        assert_api_view_name(token, TABLE_ID, kanban_view_id, RENAMED_KANBAN_VIEW)
        print(f"[ok] API: kanban view name = {RENAMED_KANBAN_VIEW!r}")

        # ── Step 4: navigate away + back → kanban rename persists ──────────
        page.goto(BASE, wait_until="domcontentloaded")
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
        page.locator(f'[data-testid="view-tab-{RENAMED_KANBAN_VIEW}"]').wait_for(
            state="visible", timeout=8000
        )
        print(f"[ok] kanban view name {RENAMED_KANBAN_VIEW!r} persists after navigation")

        if snapshot:
            page.screenshot(path="/output/views_rename_05_kanban_persists.png", full_page=True)

        browser.close()

    # ── Teardown ────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
    if r.status_code not in (200, 204):
        fatal(f"delete workspace: {r.status_code} {r.text[:200]}")
    print(f"[ok] DELETE workspace {ws_id}")

    print("\n=== PASSED — e2e_test_views_rename ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true", help="Capture screenshots at each step")
    args = parser.parse_args()
    main(snapshot=args.snapshot)
