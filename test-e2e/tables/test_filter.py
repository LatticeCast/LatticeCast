"""E2E test: JSONB filter UI — add/remove filter conditions, verify row visibility and persistence.

Scenario:
  1. Create workspace + table + 2 text columns (Name, Status) + table view.
  2. Create 4 rows: ("Alice","active"), ("Bob","inactive"), ("Carol","active"), ("Dave","")
  3. Navigate to the table page, switch to the test view.
  4. Assert all 4 rows visible.
  5. Open filter panel, add condition: Name contains "a" (matches Alice, Carol, Dave).
  6. Wait for PUT /views/{view_id} API response (persistence).
  7. Assert UI: only Alice, Carol, Dave rows visible; Bob hidden.
  8. Assert DB: view config.filter has the condition.
  9. Navigate away then back; re-activate view.
 10. Assert UI: filter still applied (Bob still hidden) — persistence verified.
 11. Add second condition: Status equals "active" (narrows to Alice, Carol).
 12. Assert UI: only Alice and Carol visible.
 13. Assert DB: config.filter has 2 conditions.
 14. Clear all filters via "Clear all" button.
 15. Assert UI: all 4 rows visible again.
 16. Test is_empty operator: add filter Status is_empty → only Dave visible.
 17. Assert DB: config.filter has is_empty condition.
 18. Remove the filter via × button; confirm all rows back.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_filter.py [--snapshot]
"""

from __future__ import annotations

import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

import os

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time())
WORKSPACE_NAME = f"filter-{_TS}"
TABLE_ID = f"filter-{_TS}"
VIEW_NAME = "Filter Test View"

SNAPSHOT = "--snapshot" in sys.argv


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


def snap(page, name: str) -> None:
    if not SNAPSHOT:
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


def visible_row_ids(page, row_ids: list[int]) -> list[int]:
    """Return which of the given row_ids have a visible grid row <tr>."""
    visible = []
    for rid in row_ids:
        loc = page.locator(f'[data-testid="grid-row-{rid}"]')
        if loc.count() > 0 and loc.first.is_visible():
            visible.append(rid)
    return visible


def main() -> None:
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

    # ── Setup: 2 text columns (Name, Status) ────────────────────────────────
    col_ids = {}
    for name in ("Name", "Status"):
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": name, "type": "text"})
        if r.status_code not in (200, 201):
            fatal(f"create column {name!r}: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        if not col:
            fatal(f"column {name!r} not found in schema")
        col_ids[name] = col["column_id"]
        print(f"[setup] column {name!r} → {col_ids[name]}")

    col_name = col_ids["Name"]
    col_status = col_ids["Status"]

    # ── Setup: 4 rows ────────────────────────────────────────────────────────
    rows_data = [
        {"Name": "Alice", "Status": "active"},
        {"Name": "Bob", "Status": "inactive"},
        {"Name": "Carol", "Status": "active"},
        {"Name": "Dave", "Status": ""},
    ]
    row_ids: list[int] = []
    for rd in rows_data:
        row_data = {col_name: rd["Name"], col_status: rd["Status"]}
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": row_data})
        if r.status_code != 201:
            fatal(f"create row {rd!r}: {r.status_code} {r.text[:200]}")
        row_ids.append(r.json()["row_id"])
    print(f"[setup] rows: {row_ids}")

    rid_alice, rid_bob, rid_carol, rid_dave = row_ids

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

        tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible")
        tab.click()

        # Wait for first row to confirm view rendered
        try:
            page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_rows")
            fatal("First row not visible after activating view")

        snap(page, "ft_01_initial")

        # ── Step 2: assert all 4 rows visible ─────────────────────────────────
        vis = visible_row_ids(page, row_ids)
        if len(vis) != 4:
            fatal(f"Expected 4 visible rows, got {len(vis)}: {vis}")
        print("[ok] all 4 rows visible initially")

        # ── Step 3: open filter panel ─────────────────────────────────────────
        filter_btn = page.locator('[data-testid="toolbar-filter-btn"]')
        try:
            filter_btn.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_toolbar")
            fatal("toolbar-filter-btn not visible")
        filter_btn.click()

        # Wait for filter panel header
        panel_header = page.locator("text=Filters (AND)")
        try:
            panel_header.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_panel")
            fatal("Filter panel did not appear")

        # ── Step 4: add condition — Name contains "a" ─────────────────────────
        add_btn = page.locator("text=+ Add condition")
        add_btn.click()

        # Wait for the filter row to appear (select elements)
        filter_row = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
        try:
            filter_row.first.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_filter_row")
            fatal("Filter condition row did not appear")

        # Select the Name column in the first dropdown
        col_select = filter_row.first.locator("select").first
        col_select.select_option(value=col_name)

        # Operator should default to "contains" — leave it
        # Fill in the value input
        value_input = filter_row.first.locator("input")

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            value_input.fill("a")

        snap(page, "ft_02_after_filter_name_contains_a")

        # ── Step 5: assert filtered rows — Alice, Carol, Dave visible; Bob hidden
        # Wait for Bob's row to disappear
        try:
            page.locator(f'[data-testid="grid-row-{rid_bob}"]').wait_for(
                state="hidden", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_bob_still_visible")
            fatal("Bob's row still visible after filter Name contains 'a'")

        vis_after = visible_row_ids(page, row_ids)
        expected = {rid_alice, rid_carol, rid_dave}
        if set(vis_after) != expected:
            fatal(f"After Name contains 'a': expected {expected}, got {set(vis_after)}")
        print("[ok] UI: Name contains 'a' → Alice, Carol, Dave visible; Bob hidden")

        # ── Step 6: verify DB ─────────────────────────────────────────────────
        view_cfg = get_view_config(token, TABLE_ID, view_id)
        filters = view_cfg.get("config", {}).get("filter", [])
        if len(filters) != 1:
            fatal(f"API: expected 1 filter condition, got {len(filters)}: {filters}")
        f0 = filters[0]
        if f0.get("colId") != col_name or f0.get("operator") != "contains" or f0.get("value") != "a":
            fatal(f"API: unexpected filter condition: {f0}")
        print("[ok] API: config.filter has Name/contains/a")

        # ── Step 7: navigate away and back — verify persistence ───────────────
        page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
        snap(page, "ft_03_away")

        wait_table_page(page, ws_name, TABLE_ID)
        tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab2.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible after reload")
        tab2.click()

        # Wait for Alice to confirm view loaded
        try:
            page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_rows_reload")
            fatal("Alice row not visible after reload")

        snap(page, "ft_04_after_reload")

        vis_reload = visible_row_ids(page, row_ids)
        if rid_bob in vis_reload:
            snap(page, "ft_FAIL_bob_visible_after_reload")
            fatal("Bob visible after reload — filter not persisted")
        if set(vis_reload) != expected:
            fatal(f"After reload: expected {expected}, got {set(vis_reload)}")
        print("[ok] UI: filter persisted after navigation")

        # ── Step 8: add second condition — Status equals "active" ─────────────
        # Re-open filter panel (it may have closed on nav)
        filter_btn2 = page.locator('[data-testid="toolbar-filter-btn"]')
        filter_btn2.click()

        panel_header2 = page.locator("text=Filters (AND)")
        try:
            panel_header2.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_panel_second")
            fatal("Filter panel did not appear for second condition")

        add_btn2 = page.locator("text=+ Add condition")
        add_btn2.click()

        # The second filter row
        filter_rows = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
        second_row = filter_rows.nth(1)
        try:
            second_row.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_second_row")
            fatal("Second filter condition row did not appear")

        # Select Status column
        col_select2 = second_row.locator("select").first
        col_select2.select_option(value=col_status)

        # Change operator to "equals"
        op_select2 = second_row.locator("select").nth(1)
        op_select2.select_option(value="equals")

        # Fill value
        value_input2 = second_row.locator("input")

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            value_input2.fill("active")

        snap(page, "ft_05_after_second_filter")

        # ── Step 9: assert only Alice and Carol visible ───────────────────────
        # Wait for Dave to disappear
        try:
            page.locator(f'[data-testid="grid-row-{rid_dave}"]').wait_for(
                state="hidden", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_dave_still_visible")
            fatal("Dave's row still visible after Status equals 'active'")

        vis_two = visible_row_ids(page, row_ids)
        expected_two = {rid_alice, rid_carol}
        if set(vis_two) != expected_two:
            fatal(f"After two filters: expected {expected_two}, got {set(vis_two)}")
        print("[ok] UI: Name contains 'a' AND Status equals 'active' → Alice, Carol")

        # ── Step 10: verify DB has 2 conditions ───────────────────────────────
        view_cfg2 = get_view_config(token, TABLE_ID, view_id)
        filters2 = view_cfg2.get("config", {}).get("filter", [])
        if len(filters2) != 2:
            fatal(f"API: expected 2 filter conditions, got {len(filters2)}: {filters2}")
        print("[ok] API: config.filter has 2 conditions")

        # ── Step 11: clear all filters ────────────────────────────────────────
        clear_btn = page.locator("text=Clear all")
        try:
            clear_btn.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_clear_btn")
            fatal("'Clear all' button not visible")

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            clear_btn.click()

        snap(page, "ft_06_after_clear")

        # ── Step 12: assert all 4 rows visible again ──────────────────────────
        try:
            page.locator(f'[data-testid="grid-row-{rid_bob}"]').wait_for(
                state="visible", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_bob_not_back")
            fatal("Bob's row not visible after clearing filters")

        vis_clear = visible_row_ids(page, row_ids)
        if len(vis_clear) != 4:
            fatal(f"Expected 4 visible rows after clear, got {len(vis_clear)}: {vis_clear}")
        print("[ok] UI: all 4 rows visible after clearing filters")

        # ── Step 13: test is_empty operator — Status is_empty → only Dave ─────
        # Panel should still be open; add a new condition
        add_btn3 = page.locator("text=+ Add condition")
        add_btn3.click()

        filter_rows3 = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
        # After "Clear all", filter rows are gone; the new one is first
        empty_row = filter_rows3.first
        try:
            empty_row.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_no_empty_row")
            fatal("Filter row for is_empty test did not appear")

        # Select Status column
        col_select3 = empty_row.locator("select").first
        col_select3.select_option(value=col_status)

        # Select is_empty operator
        op_select3 = empty_row.locator("select").nth(1)

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            op_select3.select_option(value="is_empty")

        snap(page, "ft_07_after_is_empty")

        # ── Step 14: assert only Dave visible ─────────────────────────────────
        # Wait for Alice to disappear
        try:
            page.locator(f'[data-testid="grid-row-{rid_alice}"]').wait_for(
                state="hidden", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_alice_still_visible_is_empty")
            fatal("Alice still visible after is_empty filter on Status")

        vis_empty = visible_row_ids(page, row_ids)
        if set(vis_empty) != {rid_dave}:
            fatal(f"After is_empty: expected only Dave ({rid_dave}), got {set(vis_empty)}")
        print("[ok] UI: Status is_empty → only Dave visible")

        # ── Step 15: verify DB ────────────────────────────────────────────────
        view_cfg4 = get_view_config(token, TABLE_ID, view_id)
        filters4 = view_cfg4.get("config", {}).get("filter", [])
        if len(filters4) != 1:
            fatal(f"API: expected 1 filter for is_empty, got {len(filters4)}")
        if filters4[0].get("operator") != "is_empty":
            fatal(f"API: expected is_empty operator, got {filters4[0]}")
        print("[ok] API: config.filter has is_empty condition")

        # ── Step 16: remove the filter via × button ───────────────────────────
        remove_btn = empty_row.locator('button[aria-label="Remove condition"]')

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            remove_btn.click()

        # Wait for all rows to reappear
        try:
            page.locator(f'[data-testid="grid-row-{rid_alice}"]').wait_for(
                state="visible", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ft_FAIL_alice_not_back")
            fatal("Alice not visible after removing is_empty filter")

        vis_final = visible_row_ids(page, row_ids)
        if len(vis_final) != 4:
            fatal(f"Expected 4 rows after remove, got {len(vis_final)}: {vis_final}")
        print("[ok] UI: all 4 rows visible after removing filter")

        snap(page, "ft_08_final")
        browser.close()

    # ── Teardown ──────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_view_table_filter ===")


if __name__ == "__main__":
    main()
