"""E2E test: view rename propagates everywhere.

Covers two view types (table + kanban) — renames each via UI inline input,
then verifies:
  1. UI tab label updates immediately.
  2. API (GET /tables/{table_id}) returns new name.
  3. Navigate away and back → new name persists.

Two-container architecture (developing-e2e):
  - Runs in e2e container (no Chromium).
  - Playwright connects to browser service via BROWSER_WS.
  - API checks hit BE through BASE_URL.

Usage:
    docker compose exec e2e pytest table_views/test_views_rename.py -v
    docker compose exec e2e pytest table_views/test_views_rename.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

ADMIN_USER = "lattice"
RENAMED_TABLE_VIEW = "Renamed Table"
RENAMED_KANBAN_VIEW = "Renamed Kanban"


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def get_views(token: str, table_id: str) -> list[dict]:
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r.status_code == 200, f"GET /tables/{table_id}: {r.status_code} {r.text[:200]}"
    return r.json().get("views", [])


def assert_api_view_name(token: str, table_id: str, view_id: int, expected: str) -> None:
    views = get_views(token, table_id)
    match = next((v for v in views if v["view_id"] == view_id), None)
    assert match is not None, f"view_id={view_id} not found in GET /tables/{table_id}"
    got = match.get("name")
    assert got == expected, f"API view name for view_id={view_id}: got {got!r}, want {expected!r}"


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
    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url and r.request.method == "PUT"
    ) as resp_info:
        rename_input.press("Enter")
    assert resp_info.value.ok, f"rename view API returned {resp_info.value.status}"
    page.locator(f'[data-testid="view-tab-{new_name}"]').wait_for(state="visible", timeout=5000)


def wait_table_page(page, ws_name: str, table_id: str, snapshot_enabled: bool) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        snap(page, "vr_FAIL_table_not_loaded", snapshot_enabled)
        pytest.fail(f"Table views did not finish loading for {table_id!r}")


def test_views_rename(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace
    _ts = int(time.time()) % 100000
    table_id = f"views-rename-{_ts}"

    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: blank table (no views by default — must create explicitly) ──────
    r = api("POST", "/api/v1/tables", token, json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[ok] CREATE table {table_id!r}")

    # ── Create a table-type view explicitly ────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Table View", "type": "table"})
    assert r.status_code in (200, 201), f"create table view: {r.status_code} {r.text[:200]}"
    schema = r.json()
    table_view = next((v for v in schema.get("views", []) if v.get("type") == "table"), None)
    assert table_view is not None, (
        f"table-type view not found after creation; views={schema.get('views')}"
    )
    table_view_id = table_view["view_id"]
    table_view_name = table_view["name"]
    print(f"[ok] CREATE table view id={table_view_id} name={table_view_name!r}")

    # ── Create a kanban view ───────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Kanban View", "type": "kanban"})
    assert r.status_code in (200, 201), f"create kanban view: {r.status_code} {r.text[:200]}"
    schema = r.json()
    kanban_view = next((v for v in schema.get("views", []) if v.get("type") == "kanban"), None)
    assert kanban_view is not None, (
        f"kanban view not found after creation; views={schema.get('views')}"
    )
    kanban_view_id = kanban_view["view_id"]
    kanban_view_name = kanban_view["name"]
    print(f"[ok] CREATE kanban view id={kanban_view_id} name={kanban_view_name!r}")

    # ── Navigate to table page ─────────────────────────────────────────────────
    wait_table_page(page, ws_name, table_id, snapshot)
    print("[ok] navigated to table page")

    snap(page, "vr_01_initial", snapshot)

    # ── Step 1: rename table-type view via UI ──────────────────────────────
    rename_view_via_ui(page, table_view_name, RENAMED_TABLE_VIEW)
    print(f"[ok] UI: renamed table view {table_view_name!r} → {RENAMED_TABLE_VIEW!r}")

    snap(page, "vr_02_table_renamed", snapshot)

    # API verify: BE persisted new name
    assert_api_view_name(token, table_id, table_view_id, RENAMED_TABLE_VIEW)
    print(f"[ok] API: table view name = {RENAMED_TABLE_VIEW!r}")

    # ── Step 2: navigate away + back → table rename persists ───────────────
    page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded", timeout=15000)
    wait_table_page(page, ws_name, table_id, snapshot)
    try:
        page.locator(f'[data-testid="view-tab-{RENAMED_TABLE_VIEW}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "vr_FAIL_table_tab_not_visible", snapshot)
        pytest.fail(f"table view tab {RENAMED_TABLE_VIEW!r} not visible after navigation")
    print(f"[ok] table view name {RENAMED_TABLE_VIEW!r} persists after navigation")

    snap(page, "vr_03_table_persists", snapshot)

    # ── Step 3: rename kanban view via UI ──────────────────────────────────
    rename_view_via_ui(page, kanban_view_name, RENAMED_KANBAN_VIEW)
    print(f"[ok] UI: renamed kanban view {kanban_view_name!r} → {RENAMED_KANBAN_VIEW!r}")

    snap(page, "vr_04_kanban_renamed", snapshot)

    # API verify
    assert_api_view_name(token, table_id, kanban_view_id, RENAMED_KANBAN_VIEW)
    print(f"[ok] API: kanban view name = {RENAMED_KANBAN_VIEW!r}")

    # ── Step 4: navigate away + back → kanban rename persists ─────────────
    page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded", timeout=15000)
    wait_table_page(page, ws_name, table_id, snapshot)
    try:
        page.locator(f'[data-testid="view-tab-{RENAMED_KANBAN_VIEW}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "vr_FAIL_kanban_tab_not_visible", snapshot)
        pytest.fail(f"kanban view tab {RENAMED_KANBAN_VIEW!r} not visible after navigation")
    print(f"[ok] kanban view name {RENAMED_KANBAN_VIEW!r} persists after navigation")

    snap(page, "vr_05_kanban_persists", snapshot)

    print("\n=== PASSED — test_views_rename ===")
