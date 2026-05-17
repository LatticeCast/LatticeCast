"""E2E test: column hide/show persists across navigation in the Table view.

Scenario:
  1. Create workspace + table + 3 text columns (Alpha, Beta, Gamma) + table view.
  2. Navigate to the table page, switch to the test view.
  3. Assert all 3 columns are visible in the UI.
  4. Hide column Beta via the toolbar "Hide Fields" panel (uncheck it).
  5. Wait for PUT /views/{view_id} API response (persistence).
  6. Assert UI: Beta column header is gone; Alpha and Gamma still visible.
  7. Assert DB: view config.hidden contains Beta's column_id.
  8. Navigate away (tables list) then back; re-activate view.
  9. Assert UI: Beta still hidden after reload (persisted).
 10. Unhide Beta via toolbar "Hide Fields" panel (re-check it).
 11. Wait for PUT /views/{view_id} API response.
 12. Assert UI: all 3 columns visible again.
 13. Assert DB: view config.hidden is empty or absent.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e pytest tables/test_col_hide.py -v
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


VIEW_NAME = "Hide Test View"


def get_view_config(token: str, table_id: str, view_id: int) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}/views/{view_id}", token)
    assert r.status_code == 200, f"GET view {view_id}: {r.status_code} {r.text[:200]}"
    return r.json()


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
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
        pytest.fail(f"Table page did not finish loading for {table_id!r}")


def visible_col_headers(page, col_ids: list[str]) -> list[str]:
    """Return which of the given col_ids have a visible header <th>."""
    visible = []
    for cid in col_ids:
        loc = page.locator(f'[data-testid="col-header-{cid}"]')
        if loc.count() > 0 and loc.first.is_visible():
            visible.append(cid)
    return visible


def test_col_hide_show(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace

    _TS = int(time.time())
    TABLE_ID = f"col-hide-{_TS}"

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: 3 text columns ────────────────────────────────────────────────
    col_ids = {}
    for name in ("Alpha", "Beta", "Gamma"):
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": name, "type": "text"})
        assert r.status_code in (200, 201), f"create column {name!r}: {r.status_code} {r.text[:200]}"
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        assert col, f"column {name!r} not found in schema"
        col_ids[name] = col["column_id"]
        print(f"[setup] column {name!r}")

    col_a = col_ids["Alpha"]
    col_b = col_ids["Beta"]
    col_c = col_ids["Gamma"]
    print(f"[setup] col_a={col_a} col_b={col_b} col_c={col_c}")

    # ── Setup: table view ────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": VIEW_NAME, "type": "table"})
    assert r.status_code in (200, 201), f"create view: {r.status_code} {r.text[:200]}"
    view_schema = r.json()
    view = next((v for v in view_schema.get("views", []) if v["name"] == VIEW_NAME), None)
    assert view, f"view {VIEW_NAME!r} not found in schema: {view_schema.get('views')}"
    view_id = view["view_id"]
    print(f"[setup] view {VIEW_NAME!r} id={view_id}")

    # ── Step 1: navigate and activate the view ────────────────────────────
    wait_table_page(page, ws_name, TABLE_ID)

    tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
    try:
        tab.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        pytest.fail(f"Tab {VIEW_NAME!r} not visible")
    tab.click()

    # Wait for Alpha column header to confirm view rendered
    try:
        page.wait_for_selector(f'[data-testid="col-header-{col_a}"]', timeout=8000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_cols", snapshot)
        pytest.fail(f"Column header 'Alpha' ({col_a}) not visible within 8s")

    snap(page, "ch_01_initial", snapshot)

    # ── Step 2: assert all 3 columns visible ─────────────────────────────
    vis = visible_col_headers(page, [col_a, col_b, col_c])
    assert len(vis) == 3, f"Expected 3 visible columns, got {len(vis)}: {vis}"
    print("[ok] all 3 columns visible initially")

    # ── Step 3: hide Beta via toolbar "Hide Fields" panel ─────────────────
    hide_btn = page.locator('[data-testid="toolbar-hide-fields-btn"]')
    try:
        hide_btn.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_toolbar", snapshot)
        pytest.fail("toolbar-hide-fields-btn not visible")
    hide_btn.click()

    # Wait for the "Toggle columns" header to confirm panel rendered
    toggle_header = page.locator("text=Toggle columns")
    try:
        toggle_header.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_panel", snapshot)
        pytest.fail("Hide Fields panel did not appear")

    # Find the checkbox for Beta in the panel — label contains column name
    beta_label = page.locator("label").filter(has_text="Beta")
    try:
        beta_label.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_beta_label", snapshot)
        pytest.fail("Beta label in Hide Fields panel not visible")

    beta_checkbox = beta_label.locator("input[type='checkbox']")

    # Uncheck Beta (it should be checked = visible)
    assert beta_checkbox.is_checked(), "Beta checkbox already unchecked before we hide it"

    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                  and r.request.method == "PUT",
        timeout=10000,
    ):
        beta_checkbox.click()

    snap(page, "ch_02_after_hide", snapshot)

    # Close the panel by clicking the button again
    hide_btn.click()

    # ── Step 4: assert Beta hidden, Alpha+Gamma visible ──────────────────
    # Wait for Beta column header to disappear
    try:
        page.locator(f'[data-testid="col-header-{col_b}"]').wait_for(
            state="hidden", timeout=5000
        )
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_beta_still_visible", snapshot)
        pytest.fail("Beta column header still visible after hiding")

    # Wait for Alpha to confirm table re-rendered after the config update
    try:
        page.locator(f'[data-testid="col-header-{col_a}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_alpha_gone_after_hide", snapshot)
        pytest.fail("Alpha column header disappeared after hiding Beta")

    vis_after = visible_col_headers(page, [col_a, col_b, col_c])
    assert col_b not in vis_after, f"Beta still visible after hide: {vis_after}"
    assert col_a in vis_after and col_c in vis_after, f"Alpha or Gamma missing after hiding Beta: {vis_after}"
    print("[ok] UI: Beta hidden, Alpha+Gamma visible")

    # ── Step 5: verify DB via API ─────────────────────────────────────────
    view_cfg = get_view_config(token, TABLE_ID, view_id)
    hidden_list = view_cfg.get("config", {}).get("hidden", [])
    assert col_b in hidden_list, f"API: config.hidden does not contain Beta ({col_b}); got {hidden_list}"
    print(f"[ok] API: config.hidden contains Beta")

    # ── Step 6: navigate away and back ────────────────────────────────────
    page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
    snap(page, "ch_03_away", snapshot)

    wait_table_page(page, ws_name, TABLE_ID)
    tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
    try:
        tab2.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        pytest.fail(f"Tab {VIEW_NAME!r} not visible after reload")
    tab2.click()

    # Wait for Alpha to confirm view loaded
    try:
        page.wait_for_selector(f'[data-testid="col-header-{col_a}"]', timeout=8000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_cols_reload", snapshot)
        pytest.fail("Alpha column header not visible after reload")

    snap(page, "ch_04_after_reload", snapshot)

    # ── Step 7: assert Beta still hidden after reload ─────────────────────
    vis_reload = visible_col_headers(page, [col_a, col_b, col_c])
    if col_b in vis_reload:
        snap(page, "ch_FAIL_beta_visible_after_reload", snapshot)
        pytest.fail("Beta column visible after reload — hide not persisted")
    assert col_a in vis_reload and col_c in vis_reload, f"Alpha or Gamma missing after reload: {vis_reload}"
    print("[ok] UI: Beta still hidden after navigation (persisted)")

    # ── Step 8: unhide Beta via toolbar ───────────────────────────────────
    hide_btn2 = page.locator('[data-testid="toolbar-hide-fields-btn"]')
    hide_btn2.click()

    toggle_header2 = page.locator("text=Toggle columns")
    try:
        toggle_header2.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_panel_unhide", snapshot)
        pytest.fail("Hide Fields panel did not appear for unhide")

    beta_label2 = page.locator("label").filter(has_text="Beta")
    try:
        beta_label2.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_no_beta_label_unhide", snapshot)
        pytest.fail("Beta label in Hide Fields panel not visible for unhide")

    beta_checkbox2 = beta_label2.locator("input[type='checkbox']")

    assert not beta_checkbox2.is_checked(), "Beta checkbox already checked — should be unchecked (hidden)"

    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                  and r.request.method == "PUT",
        timeout=10000,
    ):
        beta_checkbox2.click()

    # Close panel
    hide_btn2.click()

    snap(page, "ch_05_after_unhide", snapshot)

    # ── Step 9: assert all 3 columns visible again ────────────────────────
    try:
        page.locator(f'[data-testid="col-header-{col_b}"]').wait_for(
            state="visible", timeout=5000
        )
    except PlaywrightTimeout:
        snap(page, "ch_FAIL_beta_not_back", snapshot)
        pytest.fail("Beta column header not visible after unhide")

    vis_final = visible_col_headers(page, [col_a, col_b, col_c])
    assert len(vis_final) == 3, f"Expected 3 visible columns after unhide, got {len(vis_final)}: {vis_final}"
    print("[ok] UI: all 3 columns visible after unhide")

    # ── Step 10: verify DB — hidden empty or absent ───────────────────────
    view_cfg2 = get_view_config(token, TABLE_ID, view_id)
    hidden_list2 = view_cfg2.get("config", {}).get("hidden", [])
    assert col_b not in hidden_list2, f"API: config.hidden still contains Beta after unhide; got {hidden_list2}"
    print("[ok] API: config.hidden no longer contains Beta")

    snap(page, "ch_06_final", snapshot)

    print("\n=== PASSED — test_col_hide_show ===")
