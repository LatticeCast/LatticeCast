"""E2E test: Kanban '+ Add row' auto-fills group field.

Scenario:
  1. Create workspace + PM table (auto-creates Sprint Board kanban view).
  2. Navigate to the Sprint Board kanban view.
  3. Click '+ Add row' in the 'todo' lane.
  4. Assert: Create Ticket modal opens with Status pre-selected to 'todo'.
  5. Fill in a title and submit.
  6. Wait for POST /rows to fire and resolve.
  7. API verify: new row has Status = 'todo'.
  8. UI verify: new card appears in the 'todo' lane.
  9. Navigate away and back.
  10. API verify: row persists with Status = 'todo'.
  11. UI verify: card is in 'todo' lane after re-navigation.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e pytest table_views/test_kanban_add_row.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, seed_login_info


TARGET_LANE = "todo"


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        pytest.fail(f"View tabs did not load for table {table_id}")


def test_kanban_add_row(browser, admin_token, snapshot) -> None:
    token = admin_token
    _TS = int(time.time())
    WORKSPACE_NAME = f"kb-addrow-{_TS}"
    TABLE_ID = f"kb-addrow-{_TS}"
    TICKET_TITLE = f"add-row-test-{_TS}"

    print(f"[ok] login admin")

    # ── Setup: workspace ──────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── Setup: PM table (auto-creates Sprint Board kanban view) ───────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        assert r.status_code == 201, f"create PM table: {r.status_code} {r.text[:200]}"
        schema = r.json()
        columns = schema.get("columns", [])
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(columns)})")

        # Find kanban view (Sprint Board) and its group_by column
        kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
        assert kanban_views, \
            f"PM template has no kanban view; types={[v.get('type') for v in schema.get('views', [])]}"
        kanban_view = kanban_views[0]
        group_by_col_id = kanban_view.get("config", {}).get("group_by")
        assert group_by_col_id, "Kanban view has no group_by configured"
        print(f"[ok] kanban view group_by={group_by_col_id!r}")

        # Verify the target lane is a valid choice
        status_col = next((c for c in columns if c["column_id"] == group_by_col_id), None)
        assert status_col, f"Could not find group_by column {group_by_col_id!r} in schema"
        choices = [ch["value"] for ch in status_col.get("options", {}).get("choices", [])]
        assert TARGET_LANE in choices, f"Expected {TARGET_LANE!r} in choices {choices}"
        print(f"[ok] status choices include {TARGET_LANE!r}")

        # ── Playwright session ────────────────────────────────────────────────
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, "lattice", role="admin")

        goto_table(page, ws_id, TABLE_ID)

        # ── Step 1: Navigate to Sprint Board tab ──────────────────────────
        try:
            sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
            sprint_tab.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_tab", snapshot)
            pytest.fail("Sprint Board tab not visible")
        sprint_tab.click()
        print("[ok] clicked Sprint Board tab")

        # Wait for kanban to render (card-fields button is the sentinel)
        try:
            page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                state="visible", timeout=10000
            )
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_kanban", snapshot)
            pytest.fail("Kanban board did not render")

        snap(page, "kb_addrow_01_kanban_loaded", snapshot)
        print("[ok] kanban view loaded")

        # ── Step 2: Click '+ Add row' in the target lane ─────────────────
        add_btn = page.locator(f'[data-testid="kanban-add-row-{TARGET_LANE}-btn"]')
        try:
            add_btn.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_add_btn", snapshot)
            pytest.fail(f"'+ Add row' button for lane {TARGET_LANE!r} not visible")
        add_btn.click()
        print(f"[ok] clicked '+ Add row' in {TARGET_LANE!r} lane")

        # ── Step 3: Assert modal opens with group-by field pre-filled ─────
        try:
            page.locator('[data-testid="create-ticket-modal"]').wait_for(
                state="visible", timeout=5000
            )
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_modal", snapshot)
            pytest.fail("Create Ticket modal did not open after clicking '+ Add row'")

        snap(page, "kb_addrow_02_modal_open", snapshot)
        print("[ok] Create Ticket modal opened")

        # Assert the group-by (Status) select is pre-filled with target lane value
        select_el = page.locator(
            f'[data-testid="create-ticket-select-{group_by_col_id}"]'
        )
        try:
            select_el.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_select", snapshot)
            pytest.fail(
                f"Status select (data-testid=create-ticket-select-{group_by_col_id}) "
                "not visible in modal"
            )

        actual_val = select_el.input_value()
        assert actual_val == TARGET_LANE, \
            f"Modal: Status select pre-filled to {actual_val!r}, expected {TARGET_LANE!r}"
        print(f"[ok] modal Status select pre-filled to {TARGET_LANE!r}")

        # ── Step 4: Fill title and submit ─────────────────────────────────
        title_input = page.locator('[data-testid="create-ticket-title-input"]')
        try:
            title_input.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_title_input", snapshot)
            pytest.fail("Title input not visible in modal")
        title_input.fill(TICKET_TITLE)
        print(f"[ok] filled title {TICKET_TITLE!r}")

        snap(page, "kb_addrow_03_modal_filled", snapshot)

        new_row_id = None
        with page.expect_response(
            lambda resp: (
                f"/api/v1/tables/{TABLE_ID}/rows" in resp.url
                and resp.request.method == "POST"
            ),
            timeout=15000,
        ) as resp_info:
            page.locator('[data-testid="create-ticket-submit-btn"]').click()

        post_resp = resp_info.value
        assert post_resp.status == 201, f"POST /rows returned {post_resp.status}"
        new_row_id = post_resp.json().get("row_id")
        assert new_row_id, f"POST /rows response missing row_id: {post_resp.json()}"
        print(f"[ok] POST /rows → row_id={new_row_id}")

        # ── Step 5: API verify — new row has group-by field = target lane ─
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{new_row_id}", token)
        assert r.status_code == 200, f"GET row {new_row_id}: {r.status_code} {r.text[:200]}"
        row_data = r.json().get("row_data", {})
        api_val = row_data.get(group_by_col_id)
        assert api_val == TARGET_LANE, \
            f"API: row {new_row_id} has {group_by_col_id!r}={api_val!r}, expected {TARGET_LANE!r}"
        print(f"[ok] API: row {new_row_id} status={TARGET_LANE!r}")

        # ── Step 6: UI verify — card appears in target lane ───────────────
        try:
            page.locator('[data-testid="create-ticket-modal"]').wait_for(
                state="hidden", timeout=5000
            )
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_modal_not_closed", snapshot)
            pytest.fail("Create Ticket modal did not close after submit")

        target_lane_el = page.locator(f'[data-testid="kanban-lane-{TARGET_LANE}"]')
        try:
            target_lane_el.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_lane", snapshot)
            pytest.fail(f"Lane (data-testid=kanban-lane-{TARGET_LANE}) not visible")

        card_sel = f'[data-testid="kanban-card-{new_row_id}-btn"]'
        try:
            target_lane_el.locator(card_sel).wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_card_not_in_lane", snapshot)
            pytest.fail(f"Card {new_row_id} not visible in {TARGET_LANE!r} lane")

        snap(page, "kb_addrow_04_card_in_lane", snapshot)
        print(f"[ok] UI: card {new_row_id} visible in {TARGET_LANE!r} lane")

        # ── Step 7: Navigate away and back → verify persistence ───────────
        page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
        goto_table(page, ws_id, TABLE_ID)

        try:
            sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
            sprint_tab2.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_tab_after_nav", snapshot)
            pytest.fail("Sprint Board tab not visible after navigation back")
        sprint_tab2.click()

        try:
            page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                state="visible", timeout=10000
            )
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_kanban_after_nav", snapshot)
            pytest.fail("Kanban board not visible after navigation back")

        # API verify persistence
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{new_row_id}", token)
        assert r.status_code == 200, \
            f"GET row {new_row_id} after nav: {r.status_code} {r.text[:200]}"
        row_data_after = r.json().get("row_data", {})
        api_val_after = row_data_after.get(group_by_col_id)
        assert api_val_after == TARGET_LANE, \
            f"Persistence: row {new_row_id} has {group_by_col_id!r}={api_val_after!r}, " \
            f"expected {TARGET_LANE!r}"
        print(f"[ok] API: row {new_row_id} status persisted as {TARGET_LANE!r} after navigation")

        # UI verify persistence
        target_lane_el2 = page.locator(f'[data-testid="kanban-lane-{TARGET_LANE}"]')
        try:
            target_lane_el2.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_no_lane_after_nav", snapshot)
            pytest.fail(f"Lane {TARGET_LANE!r} not visible after navigation back")

        try:
            target_lane_el2.locator(card_sel).wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "kb_addrow_FAIL_card_not_persisted", snapshot)
            pytest.fail(f"Card {new_row_id} not in {TARGET_LANE!r} lane after navigation back")

        snap(page, "kb_addrow_05_persisted", snapshot)
        print(f"[ok] UI: card {new_row_id} persists in {TARGET_LANE!r} lane after navigation")

        page.close()

    finally:
        # ── Teardown: delete workspace ────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}")
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_kanban_add_row ===")
