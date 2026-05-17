"""E2E test: column rename propagates.

Topic: Renaming a column via the column-header dropdown menu persists to the
DB and is reflected in the UI immediately and after navigation away and back.

Three pillars (developing-e2e-test):
  - Playwright UI    — open col menu → click Rename → fill new name → Enter
  - BE API verify    — GET /tables/{tid} returns updated column name in columns[]
  - Durability check — navigate away and back; column header still shows new name

Flow:
  setup:  login as "lattice" → create workspace → create blank table
          → add a text column "Original Name" → create a table view
  step 1: navigate to table, wait for grid to render
  step 2: open column dropdown for our column, click Rename
          → rename input appears (col-rename-input-{col_id})
          → clear + type "Renamed Column" → press Enter
          → wait for PATCH /tables/{tid}/columns/{cid}
  step 3: API pillar — GET /tables/{tid} → column name == "Renamed Column"
  step 4: UI pillar  — col-menu-toggle text contains "Renamed Column"
  step 5: navigate away and back → col-menu-toggle still shows "Renamed Column"
  teardown: DELETE workspace (via conftest fixture)

Usage:
    docker compose exec test-e2e pytest tables/test_column_rename.py -v
    docker compose exec test-e2e pytest tables/test_column_rename.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

ADMIN_USER = "lattice"
ORIGINAL_NAME = "Original Name"
RENAMED_NAME = "Renamed Column"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_name: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-table-loaded="true"]', state="attached", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_table_not_loaded", snapshot)
        pytest.fail(f"Table {table_id!r} did not finish loading")


def test_column_rename(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace
    _ts = int(time.time()) % 100000
    table_id = f"col-ren-{_ts}"

    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create blank table ──────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    schema = r.json()
    print(f"[ok] table {table_id!r} (cols={len(schema['columns'])})")

    # ── 2. Add the column we will rename ──────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token,
            json={"name": ORIGINAL_NAME, "type": "text"})
    assert r.status_code == 201, f"add column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    col = next((c for c in schema["columns"] if c["name"] == ORIGINAL_NAME), None)
    assert col is not None, (
        f"column {ORIGINAL_NAME!r} missing after create; got {[c['name'] for c in schema['columns']]}"
    )
    col_id = col["column_id"]
    print(f"[ok] column {ORIGINAL_NAME!r} → {col_id[:8]}…")

    # ── 3. Create a table view so the grid renders ─────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code in (200, 201), f"create table view: {r.status_code} {r.text[:200]}"
    print("[ok] table view created")

    # ── 4. Browser session ─────────────────────────────────────────────────
    goto_table(page, ws_name, table_id, snapshot)
    snap(page, "col_ren_01_initial", snapshot)

    # Wait for Table view tab and click it
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    # Wait for the column header to appear in the grid
    col_toggle = f'[data-testid="col-menu-toggle-{col_id}"]'
    try:
        page.wait_for_selector(col_toggle, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_col_toggle", snapshot)
        pytest.fail(f"col-menu-toggle-{col_id[:8]}… not visible in table grid")

    # ── step 2: open column menu → click Rename ───────────────────────
    page.click(col_toggle)

    rename_btn = f'[data-testid="col-rename-btn-{col_id}"]'
    try:
        page.wait_for_selector(rename_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_rename_btn", snapshot)
        pytest.fail(f"col-rename-btn-{col_id[:8]}… not visible — missing data-testid on Rename menu item?")
    page.click(rename_btn)
    print("[ok] clicked Rename in column menu")

    # ── step 3: rename input appears; type new name + Enter ────────────
    rename_input = f'[data-testid="col-rename-input-{col_id}"]'
    try:
        page.wait_for_selector(rename_input, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_rename_input", snapshot)
        pytest.fail(f"col-rename-input-{col_id[:8]}… not visible after clicking Rename")

    snap(page, "col_ren_02_rename_input_open", snapshot)

    page.fill(rename_input, RENAMED_NAME)

    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/columns/{col_id}" in resp.url
            and resp.request.method == "PATCH"
            and resp.ok
        ),
        timeout=10000,
    ) as resp_info:
        page.press(rename_input, "Enter")

    assert resp_info.value.ok, (
        f"PATCH column returned {resp_info.value.status}: {resp_info.value.text()[:200]}"
    )
    print(f"[ok] Enter pressed; PATCH /tables/{table_id}/columns/{col_id[:8]}… confirmed")
    snap(page, "col_ren_03_after_rename", snapshot)

    # ── step 4: API pillar — GET /tables/{tid} → new name ─────────────
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r.status_code == 200, f"GET table after rename: {r.status_code} {r.text[:200]}"
    refreshed_cols = r.json()["columns"]
    updated_col = next((c for c in refreshed_cols if c["column_id"] == col_id), None)
    assert updated_col is not None, f"column {col_id[:8]}… missing from refreshed schema"
    db_name = updated_col["name"]
    assert db_name == RENAMED_NAME, f"API: column name={db_name!r}, expected {RENAMED_NAME!r}"
    print(f"[ok] API: column name persisted as {db_name!r}")

    # ── step 5: UI pillar — col-menu-toggle shows new name ────────────
    # After PATCH, refreshTable fires; the toggle button re-renders with new name.
    try:
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector('[data-testid="col-menu-toggle-{col_id}"]');
                return el && el.textContent && el.textContent.includes({repr(RENAMED_NAME)});
            }}""",
            timeout=8000,
        )
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_ui_not_updated", snapshot)
        actual = page.locator(col_toggle).text_content() or "(missing)"
        pytest.fail(
            f"UI: col-menu-toggle text did not update to {RENAMED_NAME!r} "
            f"after PATCH; got text={actual!r}"
        )
    print(f"[ok] UI: column header shows {RENAMED_NAME!r}")
    snap(page, "col_ren_04_ui_updated", snapshot)

    # ── step 6: navigate away and back → name persists ────────────────
    page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded")
    goto_table(page, ws_name, table_id, snapshot)

    # Re-click Table tab
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector(col_toggle, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_no_col_after_nav", snapshot)
        pytest.fail(f"col-menu-toggle-{col_id[:8]}… not visible after navigation back")

    try:
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector('[data-testid="col-menu-toggle-{col_id}"]');
                return el && el.textContent && el.textContent.includes({repr(RENAMED_NAME)});
            }}""",
            timeout=8000,
        )
    except PlaywrightTimeout:
        snap(page, "col_ren_FAIL_name_not_persisted", snapshot)
        actual = page.locator(col_toggle).text_content() or "(missing)"
        pytest.fail(
            f"Durability: column name did not persist after navigation; "
            f"got text={actual!r}, expected {RENAMED_NAME!r}"
        )
    print(f"[ok] Durability: column header still shows {RENAMED_NAME!r} after nav")
    snap(page, "col_ren_05_after_nav", snapshot)

    print("\n=== PASSED — test_column_rename ===")
