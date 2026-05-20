"""E2E test: search box — type query, verify row filtering, clear and restore.

Scenario:
  1. Create workspace + table + 2 text columns (Name, City) + table view.
  2. Create 4 rows: ("Alice","Tokyo"), ("Bob","Berlin"), ("Carol","Tokyo"), ("Dave","Paris")
  3. Navigate to the table page, switch to the test view.
  4. Assert all 4 rows visible.
  5. Type "tok" in search box → Alice and Carol visible (case-insensitive match on City).
  6. Clear search via × button → all 4 rows visible again.
  7. Type "bob" (lowercase) → only Bob visible (case-insensitive match on Name).
  8. Clear input via fill("") → all 4 rows visible.
  9. Type "zzz" (no match) → 0 rows visible.
 10. Reload page → all 4 rows visible (search is transient, not persisted).

Run:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest tables/test_search.py -v
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


VIEW_NAME = "Search Test View"


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


def visible_row_ids(page, row_ids: list[int]) -> list[int]:
    """Return which of the given row_ids have a visible grid row <tr>."""
    visible = []
    for rid in row_ids:
        loc = page.locator(f'[data-testid="grid-row-{rid}"]')
        if loc.count() > 0 and loc.first.is_visible():
            visible.append(rid)
    return visible


def test_search(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace

    _TS = int(time.time())
    TABLE_ID = f"search-{_TS}"

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: 2 text columns (Name, City) ──────────────────────────────────
    col_ids = {}
    for name in ("Name", "City"):
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": name, "type": "text"})
        assert r.status_code in (200, 201), f"create column {name!r}: {r.status_code} {r.text[:200]}"
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        assert col, f"column {name!r} not found in schema: {[c['name'] for c in schema.get('columns', [])]}"
        col_ids[name] = col["column_id"]
        print(f"[setup] column {name!r} → {col_ids[name]}")

    col_name = col_ids["Name"]
    col_city = col_ids["City"]

    # ── Setup: 4 rows ────────────────────────────────────────────────────────
    rows_data = [
        {"Name": "Alice", "City": "Tokyo"},
        {"Name": "Bob", "City": "Berlin"},
        {"Name": "Carol", "City": "Tokyo"},
        {"Name": "Dave", "City": "Paris"},
    ]
    row_ids: list[int] = []
    for rd in rows_data:
        row_data = {col_name: rd["Name"], col_city: rd["City"]}
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": row_data})
        assert r.status_code == 201, f"create row {rd!r}: {r.status_code} {r.text[:200]}"
        row_ids.append(r.json()["row_id"])
    print(f"[setup] rows: {row_ids}")

    rid_alice, rid_bob, rid_carol, rid_dave = row_ids

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

    try:
        page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=8000)
    except PlaywrightTimeout:
        snap(page, "search_FAIL_no_rows", snapshot)
        pytest.fail("First row not visible after activating view")

    snap(page, "search_01_initial", snapshot)

    # ── Step 2: assert all 4 rows visible ─────────────────────────────────
    vis = visible_row_ids(page, row_ids)
    assert len(vis) == 4, f"Expected 4 visible rows, got {len(vis)}: {vis}"
    print("[ok] all 4 rows visible initially")

    # ── Step 3: type "tok" → Alice and Carol visible (City=Tokyo) ─────────
    search_input = page.locator('[data-testid="toolbar-search-input"]')
    try:
        search_input.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "search_FAIL_no_input", snapshot)
        pytest.fail("Search input not visible")

    search_input.fill("tok")
    page.wait_for_timeout(500)

    snap(page, "search_02_after_tok", snapshot)

    vis_tok = visible_row_ids(page, row_ids)
    expected_tok = {rid_alice, rid_carol}
    assert set(vis_tok) == expected_tok, f"After search 'tok': expected {expected_tok}, got {set(vis_tok)}"
    print("[ok] UI: search 'tok' → Alice and Carol visible")

    # ── Step 4: clear via × button → all 4 rows visible ──────────────────
    clear_btn = page.locator('[data-testid="toolbar-search-input"] ~ button')
    try:
        clear_btn.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        snap(page, "search_FAIL_no_clear_btn", snapshot)
        pytest.fail("Search clear button not visible")
    clear_btn.click()
    page.wait_for_timeout(500)

    snap(page, "search_03_after_clear", snapshot)

    vis_clear = visible_row_ids(page, row_ids)
    assert len(vis_clear) == 4, f"Expected 4 rows after clear, got {len(vis_clear)}: {vis_clear}"
    print("[ok] UI: all 4 rows visible after clearing search")

    # ── Step 5: type "bob" (lowercase) → case-insensitive match ───────────
    search_input.fill("bob")
    page.wait_for_timeout(500)

    snap(page, "search_04_after_bob", snapshot)

    vis_bob = visible_row_ids(page, row_ids)
    assert set(vis_bob) == {rid_bob}, f"After search 'bob': expected only Bob ({rid_bob}), got {set(vis_bob)}"
    print("[ok] UI: search 'bob' (case-insensitive) → only Bob visible")

    # ── Step 6: clear by selecting all text and deleting → all rows back ──
    search_input.fill("")

    try:
        page.locator(f'[data-testid="grid-row-{rid_alice}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "search_FAIL_manual_clear", snapshot)
        pytest.fail("Rows did not reappear after manual clear")

    snap(page, "search_05_after_manual_clear", snapshot)

    vis_manual = visible_row_ids(page, row_ids)
    assert len(vis_manual) == 4, f"Expected 4 rows after manual clear, got {len(vis_manual)}: {vis_manual}"
    print("[ok] UI: all 4 rows visible after manual clear")

    # ── Step 7: type "zzz" (no match) → 0 rows visible ───────────────────
    search_input.fill("zzz")
    page.wait_for_timeout(500)

    snap(page, "search_06_after_zzz", snapshot)

    vis_zzz = visible_row_ids(page, row_ids)
    assert len(vis_zzz) == 0, f"After search 'zzz': expected 0 rows, got {len(vis_zzz)}: {vis_zzz}"
    print("[ok] UI: search 'zzz' → 0 rows visible")

    # ── Step 8: reload page to confirm search is transient (not persisted) ─
    wait_table_page(page, ws_name, TABLE_ID)

    tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
    try:
        tab2.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        pytest.fail(f"Tab {VIEW_NAME!r} not visible after reload")
    tab2.click()

    try:
        page.locator(f'[data-testid="grid-row-{rid_alice}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "search_FAIL_rows_not_back", snapshot)
        pytest.fail("Rows did not reappear after page reload")

    snap(page, "search_07_final", snapshot)

    vis_final = visible_row_ids(page, row_ids)
    assert len(vis_final) == 4, f"Expected 4 rows after reload, got {len(vis_final)}: {vis_final}"
    print("[ok] UI: all 4 rows visible after reload (search not persisted)")

    print("\n=== PASSED — test_search ===")
