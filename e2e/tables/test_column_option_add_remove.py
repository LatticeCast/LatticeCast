"""E2E test: column option add/remove — options CRUD in select column.

Topic: Adding and removing options in a select-column via ManageOptionsModal
persists to the DB and is reflected in both the Table view dropdown and the
Kanban view lanes.

Three pillars (developing-e2e):
  - Playwright UI    — open ManageOptionsModal, add option, remove option, Save
  - BE API verify    — GET /tables/{tid} confirms choices array updated
  - Cross-view check — Table view select dropdown + Kanban lanes reflect changes

Flow:
  setup:  login as "lattice" → create workspace → create PM table (Status col
          with preset options) → add Table view → add row with Status='todo'
  step 1: Table view → open Status col menu → "Manage Options"
          → add new option "blocked" → Save → wait PATCH → API verify
  step 2: UI verify — Table view select cell dropdown includes "blocked"
  step 3: open ManageOptionsModal again → remove "blocked" → Save → wait PATCH
          → API verify option gone
  step 4: UI verify — dropdown no longer includes "blocked"
  step 5: Kanban lanes reflect current options (no "blocked" lane)
  step 6: Durability — navigate away and back, verify option still absent

Usage:
    docker compose exec -T e2e pytest tables/test_column_option_add_remove.py -v
    docker compose exec -T e2e pytest tables/test_column_option_add_remove.py -v --snapshot
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

NEW_OPTION = "blocked"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_id: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_view_tabs", snapshot)
        pytest.fail(f"View tabs did not load for table {table_id}")


def open_manage_options(page, col_id: str, snapshot: bool) -> None:
    """Open column menu → click Manage Options for a given column."""
    col_toggle = f'[data-testid="col-menu-toggle-{col_id}"]'
    try:
        page.wait_for_selector(col_toggle, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_col_toggle", snapshot)
        pytest.fail(f"Column menu toggle ({col_id[:8]}…) not found")
    page.click(col_toggle)

    manage_btn = f'[data-testid="col-manage-options-{col_id}"]'
    try:
        page.wait_for_selector(manage_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_manage_btn", snapshot)
        pytest.fail("'Manage Options' menu item not visible")
    page.click(manage_btn)


def test_column_option_add_remove(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table

    print(f"[ok] login 'lattice'")

    # Find Status select column
    status_col = next(
        (c for c in columns if c.get("name") == "Status" and c.get("type") == "select"),
        None,
    )
    assert status_col, "PM template has no 'Status' select column"
    status_col_id = status_col["column_id"]
    original_choices = status_col.get("options", {}).get("choices", [])
    original_values = [c["value"] for c in original_choices]
    print(f"[ok] Status col ({status_col_id[:8]}…) choices={original_values}")

    # ── Add a Table view ─────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", admin_token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code == 201, f"add Table view: {r.status_code} {r.text[:200]}"
    print("[ok] added 'Table' view")

    # ── Add row with Status='todo' ────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
            json={"row_data": {status_col_id: "todo"}})
    assert r.status_code == 201, f"add row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] row added with Status='todo' (row_id={row_id})")

    # ── Browser session ───────────────────────────────────────────────
    goto_table(page, ws_id, table_id, snapshot)

    # Click Table view tab
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    # Wait for table grid
    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_table_grid", snapshot)
        pytest.fail("Table grid did not render")

    snap(page, "opt_crud_01_initial_table", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Add a new option "blocked"
    # ═══════════════════════════════════════════════════════════════════
    open_manage_options(page, status_col_id, snapshot)
    print("[ok] opened ManageOptionsModal for Status")

    # Type new option name and click Add
    new_input = '[data-testid="manage-options-new-input"]'
    try:
        page.wait_for_selector(new_input, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_new_input", snapshot)
        pytest.fail("manage-options-new-input not visible in modal")
    page.fill(new_input, NEW_OPTION)

    add_btn = '[data-testid="manage-options-add-btn"]'
    page.click(add_btn)
    print(f"[ok] added option {NEW_OPTION!r} in modal")

    snap(page, "opt_crud_02_after_add_in_modal", snapshot)

    # Save and wait for PATCH
    save_btn = '[data-testid="manage-options-save-btn"]'
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/columns/{status_col_id}" in resp.url
            and resp.request.method == "PATCH"
            and resp.ok
        ),
        timeout=10000,
    ):
        page.click(save_btn)
    print("[ok] Save clicked; PATCH confirmed (add)")

    snap(page, "opt_crud_03_after_save_add", snapshot)

    # ── API pillar: verify new option persisted ──────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}", admin_token)
    assert r.status_code == 200, f"GET table after add: {r.status_code} {r.text[:200]}"
    refreshed_cols = r.json()["columns"]
    updated_status = next(
        (c for c in refreshed_cols if c["column_id"] == status_col_id), None
    )
    assert updated_status, "Status column missing from refreshed schema"
    updated_choices = updated_status.get("options", {}).get("choices", [])
    updated_values = [c["value"] for c in updated_choices]
    assert NEW_OPTION in updated_values, f"API: '{NEW_OPTION}' not in choices after add; got {updated_values}"
    print(f"[ok] API: '{NEW_OPTION}' present in choices={updated_values}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: UI verify — select dropdown includes "blocked"
    # ═══════════════════════════════════════════════════════════════════
    cell_sel = f'[data-testid="select-cell-{row_id}-{status_col_id}"]'
    try:
        page.wait_for_selector(cell_sel, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_select_cell", snapshot)
        pytest.fail("select-cell not visible after save")

    # Click cell to enter edit mode (shows <select> dropdown)
    page.click(cell_sel)

    # Verify the new option exists in the <select> dropdown
    option_sel = f'{cell_sel} select option[value="{NEW_OPTION}"]'
    try:
        page.wait_for_selector(option_sel, state="attached", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_option_in_dropdown", snapshot)
        pytest.fail(f"'{NEW_OPTION}' option not found in select dropdown after add")
    print(f"[ok] UI: '{NEW_OPTION}' appears in select dropdown")

    snap(page, "opt_crud_04_dropdown_with_new_option", snapshot)

    # Click away to close edit mode
    page.click("table thead")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Remove the "blocked" option
    # ═══════════════════════════════════════════════════════════════════
    open_manage_options(page, status_col_id, snapshot)
    print("[ok] re-opened ManageOptionsModal for Status")

    # Click remove button for "blocked"
    remove_btn = f'[data-testid="choice-remove-btn-{NEW_OPTION}"]'
    try:
        page.wait_for_selector(remove_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_remove_btn", snapshot)
        pytest.fail(f"Remove button for '{NEW_OPTION}' not visible in modal")
    page.click(remove_btn)
    print(f"[ok] removed option '{NEW_OPTION}' in modal")

    snap(page, "opt_crud_05_after_remove_in_modal", snapshot)

    # Save and wait for PATCH
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/columns/{status_col_id}" in resp.url
            and resp.request.method == "PATCH"
            and resp.ok
        ),
        timeout=10000,
    ):
        page.click(save_btn)
    print("[ok] Save clicked; PATCH confirmed (remove)")

    snap(page, "opt_crud_06_after_save_remove", snapshot)

    # ── API pillar: verify option removed ────────────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}", admin_token)
    assert r.status_code == 200, f"GET table after remove: {r.status_code} {r.text[:200]}"
    refreshed_cols = r.json()["columns"]
    updated_status = next(
        (c for c in refreshed_cols if c["column_id"] == status_col_id), None
    )
    assert updated_status, "Status column missing from refreshed schema after remove"
    updated_choices = updated_status.get("options", {}).get("choices", [])
    updated_values = [c["value"] for c in updated_choices]
    assert NEW_OPTION not in updated_values, f"API: '{NEW_OPTION}' still in choices after remove; got {updated_values}"
    # Confirm original options (minus blocked) are intact
    for orig in original_values:
        assert orig in updated_values, f"API: original option '{orig}' lost after remove; got {updated_values}"
    print(f"[ok] API: '{NEW_OPTION}' removed; remaining={updated_values}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: UI verify — select dropdown no longer includes "blocked"
    # ═══════════════════════════════════════════════════════════════════
    try:
        page.wait_for_selector(cell_sel, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_select_cell_after_remove", snapshot)
        pytest.fail("select-cell not visible after remove save")

    page.click(cell_sel)

    # Option should NOT be in the dropdown
    option_locator = page.locator(f'{cell_sel} select option[value="{NEW_OPTION}"]')
    count = option_locator.count()
    assert count == 0, f"'{NEW_OPTION}' still in select dropdown after remove (count={count})"
    print(f"[ok] UI: '{NEW_OPTION}' no longer in select dropdown")

    # Click away to close edit mode
    page.click("table thead")

    snap(page, "opt_crud_07_dropdown_without_removed", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Kanban view — lanes reflect current options
    # ═══════════════════════════════════════════════════════════════════
    sprint_tab = '[data-testid="view-tab-Sprint Board"]'
    try:
        page.wait_for_selector(sprint_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_sprint_tab", snapshot)
        pytest.fail("Sprint Board tab not visible")
    page.click(sprint_tab)
    print("[ok] switched to Sprint Board (kanban)")

    # 'todo' lane should exist (it's an original option with a row)
    lane_todo = '[data-testid="kanban-lane-header-todo"]'
    try:
        page.wait_for_selector(lane_todo, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_todo_lane", snapshot)
        pytest.fail("kanban-lane-header-todo not visible")
    print("[ok] Kanban: 'todo' lane visible")

    # 'blocked' lane should NOT exist
    lane_blocked = f'[data-testid="kanban-lane-header-{NEW_OPTION}"]'
    blocked_count = page.locator(lane_blocked).count()
    assert blocked_count == 0, f"Kanban: lane for '{NEW_OPTION}' still exists after removal"
    print(f"[ok] Kanban: no lane for '{NEW_OPTION}' (correctly removed)")

    snap(page, "opt_crud_08_kanban_no_blocked_lane", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: Durability — navigate away and back
    # ═══════════════════════════════════════════════════════════════════
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id, snapshot)

    # Switch to Table view
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_grid_after_nav", snapshot)
        pytest.fail("Table grid did not render after navigation back")

    # Verify option is still absent in dropdown after nav
    try:
        page.wait_for_selector(cell_sel, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_cell_after_nav", snapshot)
        pytest.fail("select-cell not visible after nav back")
    page.click(cell_sel)

    option_locator_after_nav = page.locator(f'{cell_sel} select option[value="{NEW_OPTION}"]')
    count_after_nav = option_locator_after_nav.count()
    assert count_after_nav == 0, f"'{NEW_OPTION}' reappeared in dropdown after navigation"
    print(f"[ok] UI (after nav): '{NEW_OPTION}' still absent from dropdown")

    snap(page, "opt_crud_09_after_nav_dropdown_clean", snapshot)

    print("\n=== PASSED — test_column_option_add_remove ===")
