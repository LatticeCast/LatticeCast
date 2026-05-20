"""E2E test: e2e_test_column_url_type — url cell renders + click.

Topic: A URL column cell renders as a clickable hyperlink when the stored
value has an http/https protocol, shows an empty placeholder when blank,
and the stored value is confirmed in the DB via the BE API.

Three pillars (developing-e2e):
  - Playwright UI    — grid shows <a> link with correct href; empty cell
                       shows '—' placeholder
  - BE API verify    — GET /rows/{row_id} returns correct URL in row_data
  - Durability check — navigate away and back; link still renders correctly

Flow:
  setup:  login as "lattice" → create workspace → create blank table
          → add a url column "Website" → create a table view
          → create two rows: row1 has https URL, row2 is empty
  step 1: navigate to table, click Table view tab, wait for grid
  step 2: API pillar — GET /rows/{row_id} confirms stored URL
  step 3: UI pillar  — url-cell-{row1_id}-{col_id} anchor has correct href
                       url-cell-empty-{row2_id}-{col_id} shows '—'
  step 4: navigate away and back → link still renders
  teardown: DELETE workspace

Usage:
    docker compose exec -T e2e pytest tables/test_column_url_type.py -v
    docker compose exec -T e2e pytest tables/test_column_url_type.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, login, seed_login_info

ADMIN_USER = "lattice"
COL_NAME = "Website"
TEST_URL = "https://example.com"


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
        snap(page, "url_FAIL_table_not_loaded", snapshot)
        pytest.fail(f"Table {table_id!r} did not finish loading")


def test_column_url_type(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace
    _TS = int(time.time()) % 100000
    TABLE_ID = f"url-{_TS}"

    print(f"[ok] login {ADMIN_USER!r}")

    # ── 2. Create blank table ──────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    schema = r.json()
    print(f"[ok] table {TABLE_ID!r} (cols={len(schema['columns'])})")

    # ── 3. Add URL column ──────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
            json={"name": COL_NAME, "type": "url"})
    assert r.status_code == 201, f"add url column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    col = next((c for c in schema["columns"] if c["name"] == COL_NAME), None)
    assert col is not None, f"column {COL_NAME!r} missing after create; got {[c['name'] for c in schema['columns']]}"
    col_id = col["column_id"]
    print(f"[ok] url column {COL_NAME!r} → {col_id[:8]}…")

    # ── 4. Create table view ───────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code in (200, 201), f"create table view: {r.status_code} {r.text[:200]}"
    print("[ok] table view created")

    # ── 5. Create row1 with a URL value ───────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
            json={"row_data": {col_id: TEST_URL}})
    assert r.status_code in (200, 201), f"create row1: {r.status_code} {r.text[:200]}"
    row1 = r.json()
    row1_id = row1["row_id"]
    print(f"[ok] row1 id={row1_id} url={TEST_URL!r}")

    # ── 6. Create row2 with empty URL ─────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
            json={"row_data": {}})
    assert r.status_code in (200, 201), f"create row2: {r.status_code} {r.text[:200]}"
    row2 = r.json()
    row2_id = row2["row_id"]
    print(f"[ok] row2 id={row2_id} (empty url)")

    # ── 7. API pillar: verify row1 stores the URL ─────────────────────────
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row1_id}", token)
    assert r.status_code == 200, f"GET row1: {r.status_code} {r.text[:200]}"
    stored_url = r.json()["row_data"].get(col_id, "")
    assert stored_url == TEST_URL, f"API: row1 url={stored_url!r}, expected {TEST_URL!r}"
    print(f"[ok] API: row1 url stored correctly as {stored_url!r}")

    # ── 8. Browser session ─────────────────────────────────────────────────
    goto_table(page, ws_name, TABLE_ID, snapshot)
    snap(page, "url_01_initial", snapshot)

    # Click Table view tab
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "url_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    # ── step 3a: UI — url-cell link for row1 renders with correct href ─
    url_cell = f'[data-testid="url-cell-{row1_id}-{col_id}"]'
    try:
        page.wait_for_selector(url_cell, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "url_FAIL_no_url_cell", snapshot)
        pytest.fail(
            f"url-cell-{row1_id}-{col_id[:8]}… not visible — "
            "missing data-testid on URL anchor in TableGrid?"
        )

    href = page.get_attribute(url_cell, "href")
    assert href == TEST_URL, f"url-cell href={href!r}, expected {TEST_URL!r}"
    print(f"[ok] UI: url-cell anchor href={href!r}")

    link_text = page.locator(url_cell).text_content() or ""
    assert TEST_URL in link_text, f"url-cell text={link_text!r}, expected to contain {TEST_URL!r}"
    print(f"[ok] UI: url-cell text content matches URL")

    snap(page, "url_02_url_cell_visible", snapshot)

    # ── step 3b: UI — empty cell shows placeholder '—' ─────────────────
    empty_cell = f'[data-testid="url-cell-empty-{row2_id}-{col_id}"]'
    try:
        page.wait_for_selector(empty_cell, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "url_FAIL_no_empty_cell", snapshot)
        pytest.fail(
            f"url-cell-empty-{row2_id}-{col_id[:8]}… not visible — "
            "missing data-testid on empty URL span in TableGrid?"
        )

    placeholder_text = page.locator(empty_cell).text_content() or ""
    assert "—" in placeholder_text, f"empty url-cell text={placeholder_text!r}, expected '—'"
    print("[ok] UI: empty url-cell shows '—' placeholder")

    snap(page, "url_03_empty_cell_visible", snapshot)

    # ── step 4: durability — navigate away and back ────────────────────
    page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded")
    goto_table(page, ws_name, TABLE_ID, snapshot)

    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "url_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector(url_cell, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "url_FAIL_no_url_cell_after_nav", snapshot)
        pytest.fail(f"url-cell-{row1_id}-{col_id[:8]}… not visible after navigation back")

    href_after = page.get_attribute(url_cell, "href")
    assert href_after == TEST_URL, f"Durability: href={href_after!r} after nav, expected {TEST_URL!r}"
    print(f"[ok] Durability: url-cell href still {href_after!r} after nav")

    snap(page, "url_04_after_nav", snapshot)

    print("\n=== PASSED — e2e_test_column_url_type ===")
