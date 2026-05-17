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
    docker compose exec test-e2e pytest tables/test_filter.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, login, seed_login_info


VIEW_NAME = "Filter Test View"


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


def visible_row_ids(page, row_ids: list[int]) -> list[int]:
    """Return which of the given row_ids have a visible grid row <tr>."""
    visible = []
    for rid in row_ids:
        loc = page.locator(f'[data-testid="grid-row-{rid}"]')
        if loc.count() > 0 and loc.first.is_visible():
            visible.append(rid)
    return visible


def test_view_table_filter(browser, admin_token, snapshot) -> None:
    token = admin_token
    _TS = int(time.time())
    WORKSPACE_NAME = f"filter-{_TS}"
    TABLE_ID = f"filter-{_TS}"

    # ── Setup: workspace ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    try:
        # ── Setup: table ─────────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
        assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
        print(f"[setup] table {TABLE_ID!r}")

        # ── Setup: 2 text columns (Name, Status) ────────────────────────────
        col_ids = {}
        for name in ("Name", "Status"):
            r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                    json={"name": name, "type": "text"})
            assert r.status_code in (200, 201), f"create column {name!r}: {r.status_code} {r.text[:200]}"
            schema = r.json()
            col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
            assert col, f"column {name!r} not found in schema"
            col_ids[name] = col["column_id"]
            print(f"[setup] column {name!r} → {col_ids[name]}")

        col_name = col_ids["Name"]
        col_status = col_ids["Status"]

        # ── Setup: 4 rows ────────────────────────────────────────────────────
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
            assert r.status_code == 201, f"create row {rd!r}: {r.status_code} {r.text[:200]}"
            row_ids.append(r.json()["row_id"])
        print(f"[setup] rows: {row_ids}")

        rid_alice, rid_bob, rid_carol, rid_dave = row_ids

        # ── Setup: table view ────────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": VIEW_NAME, "type": "table"})
        assert r.status_code in (200, 201), f"create view: {r.status_code} {r.text[:200]}"
        view_schema = r.json()
        view = next((v for v in view_schema.get("views", []) if v["name"] == VIEW_NAME), None)
        assert view, f"view {VIEW_NAME!r} not found in schema: {view_schema.get('views')}"
        view_id = view["view_id"]
        print(f"[setup] view {VIEW_NAME!r} id={view_id}")

        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        seed_login_info(ctx, token, "lattice", role="admin")
        page = ctx.new_page()

        try:
            # ── Step 1: navigate and activate the view ────────────────────────
            wait_table_page(page, ws_name, TABLE_ID)

            tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
            try:
                tab.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeout:
                pytest.fail(f"Tab {VIEW_NAME!r} not visible")
            tab.click()

            # Wait for first row to confirm view rendered
            try:
                page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=8000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_rows", snapshot)
                pytest.fail("First row not visible after activating view")

            snap(page, "ft_01_initial", snapshot)

            # ── Step 2: assert all 4 rows visible ─────────────────────────────
            vis = visible_row_ids(page, row_ids)
            assert len(vis) == 4, f"Expected 4 visible rows, got {len(vis)}: {vis}"
            print("[ok] all 4 rows visible initially")

            # ── Step 3: open filter panel ─────────────────────────────────────
            filter_btn = page.locator('[data-testid="toolbar-filter-btn"]')
            try:
                filter_btn.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_toolbar", snapshot)
                pytest.fail("toolbar-filter-btn not visible")
            filter_btn.click()

            # Wait for filter panel header
            panel_header = page.locator("text=Filters (AND)")
            try:
                panel_header.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_panel", snapshot)
                pytest.fail("Filter panel did not appear")

            # ── Step 4: add condition — Name contains "a" ─────────────────────
            add_btn = page.locator("text=+ Add condition")
            add_btn.click()

            # Wait for the filter row to appear (select elements)
            filter_row = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
            try:
                filter_row.first.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_filter_row", snapshot)
                pytest.fail("Filter condition row did not appear")

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

            snap(page, "ft_02_after_filter_name_contains_a", snapshot)

            # ── Step 5: assert filtered rows — Alice, Carol, Dave visible; Bob hidden
            # Wait for Bob's row to disappear
            try:
                page.locator(f'[data-testid="grid-row-{rid_bob}"]').wait_for(
                    state="hidden", timeout=8000
                )
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_bob_still_visible", snapshot)
                pytest.fail("Bob's row still visible after filter Name contains 'a'")

            vis_after = visible_row_ids(page, row_ids)
            expected = {rid_alice, rid_carol, rid_dave}
            assert set(vis_after) == expected, f"After Name contains 'a': expected {expected}, got {set(vis_after)}"
            print("[ok] UI: Name contains 'a' → Alice, Carol, Dave visible; Bob hidden")

            # ── Step 6: verify DB ─────────────────────────────────────────────
            view_cfg = get_view_config(token, TABLE_ID, view_id)
            filters = view_cfg.get("config", {}).get("filter", [])
            assert len(filters) == 1, f"API: expected 1 filter condition, got {len(filters)}: {filters}"
            f0 = filters[0]
            assert f0.get("colId") == col_name and f0.get("operator") == "contains" and f0.get("value") == "a", \
                f"API: unexpected filter condition: {f0}"
            print("[ok] API: config.filter has Name/contains/a")

            # ── Step 7: navigate away and back — verify persistence ───────────
            page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
            snap(page, "ft_03_away", snapshot)

            wait_table_page(page, ws_name, TABLE_ID)
            tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
            try:
                tab2.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeout:
                pytest.fail(f"Tab {VIEW_NAME!r} not visible after reload")
            tab2.click()

            # Wait for Alice to confirm view loaded
            try:
                page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=8000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_rows_reload", snapshot)
                pytest.fail("Alice row not visible after reload")

            snap(page, "ft_04_after_reload", snapshot)

            vis_reload = visible_row_ids(page, row_ids)
            if rid_bob in vis_reload:
                snap(page, "ft_FAIL_bob_visible_after_reload", snapshot)
                pytest.fail("Bob visible after reload — filter not persisted")
            assert set(vis_reload) == expected, f"After reload: expected {expected}, got {set(vis_reload)}"
            print("[ok] UI: filter persisted after navigation")

            # ── Step 8: add second condition — Status equals "active" ─────────
            # Re-open filter panel (it may have closed on nav)
            filter_btn2 = page.locator('[data-testid="toolbar-filter-btn"]')
            filter_btn2.click()

            panel_header2 = page.locator("text=Filters (AND)")
            try:
                panel_header2.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_panel_second", snapshot)
                pytest.fail("Filter panel did not appear for second condition")

            add_btn2 = page.locator("text=+ Add condition")
            add_btn2.click()

            # The second filter row
            filter_rows = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
            second_row = filter_rows.nth(1)
            try:
                second_row.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_second_row", snapshot)
                pytest.fail("Second filter condition row did not appear")

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

            snap(page, "ft_05_after_second_filter", snapshot)

            # ── Step 9: assert only Alice and Carol visible ───────────────────
            # Wait for Dave to disappear
            try:
                page.locator(f'[data-testid="grid-row-{rid_dave}"]').wait_for(
                    state="hidden", timeout=8000
                )
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_dave_still_visible", snapshot)
                pytest.fail("Dave's row still visible after Status equals 'active'")

            vis_two = visible_row_ids(page, row_ids)
            expected_two = {rid_alice, rid_carol}
            assert set(vis_two) == expected_two, f"After two filters: expected {expected_two}, got {set(vis_two)}"
            print("[ok] UI: Name contains 'a' AND Status equals 'active' → Alice, Carol")

            # ── Step 10: verify DB has 2 conditions ───────────────────────────
            view_cfg2 = get_view_config(token, TABLE_ID, view_id)
            filters2 = view_cfg2.get("config", {}).get("filter", [])
            assert len(filters2) == 2, f"API: expected 2 filter conditions, got {len(filters2)}: {filters2}"
            print("[ok] API: config.filter has 2 conditions")

            # ── Step 11: clear all filters ────────────────────────────────────
            clear_btn = page.locator("text=Clear all")
            try:
                clear_btn.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_clear_btn", snapshot)
                pytest.fail("'Clear all' button not visible")

            with page.expect_response(
                lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                          and r.request.method == "PUT",
                timeout=10000,
            ):
                clear_btn.click()

            snap(page, "ft_06_after_clear", snapshot)

            # ── Step 12: assert all 4 rows visible again ──────────────────────
            try:
                page.locator(f'[data-testid="grid-row-{rid_bob}"]').wait_for(
                    state="visible", timeout=8000
                )
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_bob_not_back", snapshot)
                pytest.fail("Bob's row not visible after clearing filters")

            vis_clear = visible_row_ids(page, row_ids)
            assert len(vis_clear) == 4, f"Expected 4 visible rows after clear, got {len(vis_clear)}: {vis_clear}"
            print("[ok] UI: all 4 rows visible after clearing filters")

            # ── Step 13: test is_empty operator — Status is_empty → only Dave ─
            # Panel should still be open; add a new condition
            add_btn3 = page.locator("text=+ Add condition")
            add_btn3.click()

            filter_rows3 = page.locator(".border-b.border-gray-200.bg-gray-50 .mb-2.flex.items-center.gap-2")
            # After "Clear all", filter rows are gone; the new one is first
            empty_row = filter_rows3.first
            try:
                empty_row.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_no_empty_row", snapshot)
                pytest.fail("Filter row for is_empty test did not appear")

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

            snap(page, "ft_07_after_is_empty", snapshot)

            # ── Step 14: assert only Dave visible ─────────────────────────────
            # Wait for Alice to disappear
            try:
                page.locator(f'[data-testid="grid-row-{rid_alice}"]').wait_for(
                    state="hidden", timeout=8000
                )
            except PlaywrightTimeout:
                snap(page, "ft_FAIL_alice_still_visible_is_empty", snapshot)
                pytest.fail("Alice still visible after is_empty filter on Status")

            vis_empty = visible_row_ids(page, row_ids)
            assert set(vis_empty) == {rid_dave}, f"After is_empty: expected only Dave ({rid_dave}), got {set(vis_empty)}"
            print("[ok] UI: Status is_empty → only Dave visible")

            # ── Step 15: verify DB ────────────────────────────────────────────
            view_cfg4 = get_view_config(token, TABLE_ID, view_id)
            filters4 = view_cfg4.get("config", {}).get("filter", [])
            assert len(filters4) == 1, f"API: expected 1 filter for is_empty, got {len(filters4)}"
            assert filters4[0].get("operator") == "is_empty", f"API: expected is_empty operator, got {filters4[0]}"
            print("[ok] API: config.filter has is_empty condition")

            # ── Step 16: remove the filter via × button ───────────────────────
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
                snap(page, "ft_FAIL_alice_not_back", snapshot)
                pytest.fail("Alice not visible after removing is_empty filter")

            vis_final = visible_row_ids(page, row_ids)
            assert len(vis_final) == 4, f"Expected 4 rows after remove, got {len(vis_final)}: {vis_final}"
            print("[ok] UI: all 4 rows visible after removing filter")

            snap(page, "ft_08_final", snapshot)

        finally:
            page.close()
            ctx.close()

    finally:
        # ── Teardown ──────────────────────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
        if r.status_code not in (200, 204):
            print(f"warn: delete workspace returned {r.status_code}")
        else:
            print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_view_table_filter ===")
