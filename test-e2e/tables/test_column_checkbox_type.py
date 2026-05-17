"""E2E test: checkbox column toggle.

Topic: A checkbox column cell renders as a toggle switch, clicking it
flips the value (false→true, true→false), the new state is persisted
to the DB via the BE API, and survives navigation.

Three pillars (developing-e2e-test):
  - Playwright UI    — checkbox button renders with correct aria-checked
                       state, clicking toggles it
  - BE API verify    — GET /rows/{row_id} confirms stored boolean value
  - Durability check — navigate away and back; toggled state persists

Flow:
  setup:  login as "lattice" → create workspace → create blank table
          → add a checkbox column "Done" → create a table view
          → create one row with checkbox=false
  step 1: navigate to table, click Table view tab, wait for grid
  step 2: API pillar — GET /rows/{row_id} confirms initial value (false)
  step 3: UI pillar  — checkbox-cell renders with aria-checked="false"
  step 4: Click checkbox → UI shows aria-checked="true"
  step 5: API pillar — GET /rows/{row_id} confirms value flipped to true
  step 6: Click again → UI shows aria-checked="false"
  step 7: API pillar — GET /rows/{row_id} confirms value back to false
  step 8: Toggle back to true, navigate away and back → still true
  teardown: DELETE workspace

Usage:
    docker compose exec -T test-e2e pytest tables/test_column_checkbox_type.py -v
    docker compose exec -T test-e2e pytest tables/test_column_checkbox_type.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

COL_NAME = "Done"


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
        snap(page, "chk_FAIL_table_not_loaded", snapshot)
        pytest.fail(f"Table {table_id!r} did not finish loading")


def test_checkbox_toggle(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace

    _ts = int(time.time()) % 100000
    table_id = f"chk-{_ts}"

    # ── 1. Create blank table ──────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    schema = r.json()
    print(f"[ok] table {table_id!r} (cols={len(schema['columns'])})")

    # ── 2. Add checkbox column ─────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token,
            json={"name": COL_NAME, "type": "checkbox"})
    assert r.status_code == 201, f"add checkbox column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    col = next((c for c in schema["columns"] if c["name"] == COL_NAME), None)
    assert col is not None, f"column {COL_NAME!r} missing after create; got {[c['name'] for c in schema['columns']]}"
    col_id = col["column_id"]
    print(f"[ok] checkbox column {COL_NAME!r} → {col_id[:8]}…")

    # ── 3. Create table view ───────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code in (200, 201), f"create table view: {r.status_code} {r.text[:200]}"
    print("[ok] table view created")

    # ── 4. Create row with checkbox=false ──────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/rows", token,
            json={"row_data": {col_id: False}})
    assert r.status_code in (200, 201), f"create row: {r.status_code} {r.text[:200]}"
    row = r.json()
    row_id = row["row_id"]
    print(f"[ok] row id={row_id} checkbox=false")

    # ── 5. API pillar: verify initial value (false) ────────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row: {r.status_code} {r.text[:200]}"
    stored = r.json()["row_data"].get(col_id)
    assert stored is False, f"API: initial checkbox={stored!r}, expected False"
    print("[ok] API: initial checkbox=False confirmed")

    # ── 6. Browser session ─────────────────────────────────────────────────
    goto_table(page, ws_name, table_id, snapshot)
    snap(page, "chk_01_initial", snapshot)

    # Click Table view tab
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "chk_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    # ── step 3: UI — checkbox renders with aria-checked=false ──────────
    chk_sel = f'[data-testid="checkbox-cell-{row_id}-{col_id}"]'
    try:
        page.wait_for_selector(chk_sel, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "chk_FAIL_no_checkbox_cell", snapshot)
        pytest.fail(
            f"checkbox-cell-{row_id}-{col_id[:8]}… not visible — "
            "missing data-testid on checkbox button in TableGrid?"
        )

    aria = page.get_attribute(chk_sel, "aria-checked")
    if aria != "false":
        snap(page, "chk_FAIL_initial_aria", snapshot)
        pytest.fail(f"UI: initial aria-checked={aria!r}, expected 'false'")
    print("[ok] UI: checkbox aria-checked='false' (initial)")
    snap(page, "chk_02_initial_false", snapshot)

    # ── step 4: Click checkbox → toggles to true ───────────────────────
    with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
        page.click(chk_sel)
    resp_info.value

    # Wait for UI to update
    page.wait_for_function(
        f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "true"',
        timeout=5000,
    )
    aria = page.get_attribute(chk_sel, "aria-checked")
    if aria != "true":
        snap(page, "chk_FAIL_toggle_true", snapshot)
        pytest.fail(f"UI: after click aria-checked={aria!r}, expected 'true'")
    print("[ok] UI: checkbox toggled to aria-checked='true'")
    snap(page, "chk_03_toggled_true", snapshot)

    # ── step 5: API pillar — verify toggled to true ────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row after toggle: {r.status_code} {r.text[:200]}"
    stored = r.json()["row_data"].get(col_id)
    assert stored is True, f"API: after toggle checkbox={stored!r}, expected True"
    print("[ok] API: checkbox=True confirmed after toggle")

    # ── step 6: Click again → toggles back to false ────────────────────
    with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
        page.click(chk_sel)
    resp_info.value

    page.wait_for_function(
        f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "false"',
        timeout=5000,
    )
    aria = page.get_attribute(chk_sel, "aria-checked")
    if aria != "false":
        snap(page, "chk_FAIL_toggle_false", snapshot)
        pytest.fail(f"UI: after 2nd click aria-checked={aria!r}, expected 'false'")
    print("[ok] UI: checkbox toggled back to aria-checked='false'")
    snap(page, "chk_04_toggled_false", snapshot)

    # ── step 7: API pillar — verify back to false ──────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row after 2nd toggle: {r.status_code} {r.text[:200]}"
    stored = r.json()["row_data"].get(col_id)
    assert stored is False, f"API: after 2nd toggle checkbox={stored!r}, expected False"
    print("[ok] API: checkbox=False confirmed after 2nd toggle")

    # ── step 8: Durability — toggle to true, navigate away and back ────
    with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
        page.click(chk_sel)
    resp_info.value

    page.wait_for_function(
        f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "true"',
        timeout=5000,
    )
    print("[ok] UI: checkbox set to true for durability check")

    page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded")
    goto_table(page, ws_name, table_id, snapshot)

    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "chk_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector(chk_sel, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "chk_FAIL_no_checkbox_after_nav", snapshot)
        pytest.fail("checkbox-cell not visible after navigation back")

    aria = page.get_attribute(chk_sel, "aria-checked")
    if aria != "true":
        snap(page, "chk_FAIL_durability", snapshot)
        pytest.fail(f"Durability: aria-checked={aria!r} after nav, expected 'true'")
    print("[ok] Durability: checkbox still true after navigation")

    # API confirm durability
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row durability: {r.status_code} {r.text[:200]}"
    stored = r.json()["row_data"].get(col_id)
    assert stored is True, f"API durability: checkbox={stored!r}, expected True"
    print("[ok] API: durability confirmed checkbox=True")

    snap(page, "chk_05_durability_pass", snapshot)

    print("\n=== PASSED — test_column_checkbox_type ===")
