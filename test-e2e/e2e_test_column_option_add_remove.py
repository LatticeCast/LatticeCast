#!/usr/bin/env python3
"""E2E test: e2e_test_column_option_add_remove — options CRUD in select column.

Topic: Adding and removing options in a select-column via ManageOptionsModal
persists to the DB and is reflected in both the Table view dropdown and the
Kanban view lanes.

Three pillars (developing-e2e-test):
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
  teardown: DELETE workspace

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_column_option_add_remove.py
    docker compose exec test-e2e python3 /scripts/e2e_test_column_option_add_remove.py --snapshot
"""

from __future__ import annotations

import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from e2e_base import BASE, BROWSER_WS, fatal, login, api, seed_login_info

ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WORKSPACE_NAME = f"e2e-opt-crud-{_SUFFIX}"
TABLE_ID = f"opt-crud-{_SUFFIX}"
NEW_OPTION = "blocked"

SNAPSHOT = "--snapshot" in sys.argv


def snap(page, name: str) -> None:
    if SNAPSHOT:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_view_tabs")
        fatal(f"View tabs did not load for table {table_id}")


def open_manage_options(page, col_id: str) -> None:
    """Open column menu → click Manage Options for a given column."""
    col_toggle = f'[data-testid="col-menu-toggle-{col_id}"]'
    try:
        page.wait_for_selector(col_toggle, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_col_toggle")
        fatal(f"Column menu toggle ({col_id[:8]}…) not found")
    page.click(col_toggle)

    manage_btn = f'[data-testid="col-manage-options-{col_id}"]'
    try:
        page.wait_for_selector(manage_btn, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "opt_crud_FAIL_no_manage_btn")
        fatal("'Manage Options' menu item not visible")
    page.click(manage_btn)


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create workspace ──────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── 2. Create PM table ───────────────────────────────────────────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(schema['columns'])})")

        # Find Status select column
        status_col = next(
            (c for c in schema["columns"] if c.get("name") == "Status" and c.get("type") == "select"),
            None,
        )
        if not status_col:
            fatal(f"PM template has no 'Status' select column")
        status_col_id = status_col["column_id"]
        original_choices = status_col.get("options", {}).get("choices", [])
        original_values = [c["value"] for c in original_choices]
        print(f"[ok] Status col ({status_col_id[:8]}…) choices={original_values}")

        # ── 2b. Add a Table view ─────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Table", "type": "table", "config": {}})
        if r.status_code != 201:
            fatal(f"add Table view: {r.status_code} {r.text[:200]}")
        print("[ok] added 'Table' view")

        # ── 3. Add row with Status='todo' ────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {status_col_id: "todo"}})
        if r.status_code != 201:
            fatal(f"add row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] row added with Status='todo' (row_id={row_id})")

        # ── 4. Browser session ───────────────────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.connect(BROWSER_WS)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            seed_login_info(page, token, ADMIN_USER)

            goto_table(page, ws_id, TABLE_ID)

            # Click Table view tab
            table_tab = '[data-testid="view-tab-Table"]'
            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_table_tab")
                fatal("'Table' view tab not visible")
            page.click(table_tab)

            # Wait for table grid
            try:
                page.wait_for_selector("table thead", state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_table_grid")
                fatal("Table grid did not render")

            snap(page, "opt_crud_01_initial_table")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 1: Add a new option "blocked"
            # ═══════════════════════════════════════════════════════════════════
            open_manage_options(page, status_col_id)
            print("[ok] opened ManageOptionsModal for Status")

            # Type new option name and click Add
            new_input = '[data-testid="manage-options-new-input"]'
            try:
                page.wait_for_selector(new_input, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_new_input")
                fatal("manage-options-new-input not visible in modal")
            page.fill(new_input, NEW_OPTION)

            add_btn = '[data-testid="manage-options-add-btn"]'
            page.click(add_btn)
            print(f"[ok] added option {NEW_OPTION!r} in modal")

            snap(page, "opt_crud_02_after_add_in_modal")

            # Save and wait for PATCH
            save_btn = '[data-testid="manage-options-save-btn"]'
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/columns/{status_col_id}" in resp.url
                    and resp.request.method == "PATCH"
                    and resp.ok
                ),
                timeout=10000,
            ):
                page.click(save_btn)
            print("[ok] Save clicked; PATCH confirmed (add)")

            snap(page, "opt_crud_03_after_save_add")

            # ── API pillar: verify new option persisted ──────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r.status_code != 200:
                fatal(f"GET table after add: {r.status_code} {r.text[:200]}")
            refreshed_cols = r.json()["columns"]
            updated_status = next(
                (c for c in refreshed_cols if c["column_id"] == status_col_id), None
            )
            if not updated_status:
                fatal("Status column missing from refreshed schema")
            updated_choices = updated_status.get("options", {}).get("choices", [])
            updated_values = [c["value"] for c in updated_choices]
            if NEW_OPTION not in updated_values:
                fatal(f"API: '{NEW_OPTION}' not in choices after add; got {updated_values}")
            print(f"[ok] API: '{NEW_OPTION}' present in choices={updated_values}")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 2: UI verify — select dropdown includes "blocked"
            # ═══════════════════════════════════════════════════════════════════
            cell_sel = f'[data-testid="select-cell-{row_id}-{status_col_id}"]'
            try:
                page.wait_for_selector(cell_sel, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_select_cell")
                fatal("select-cell not visible after save")

            # Click cell to enter edit mode (shows <select> dropdown)
            page.click(cell_sel)

            # Verify the new option exists in the <select> dropdown
            option_sel = f'{cell_sel} select option[value="{NEW_OPTION}"]'
            try:
                page.wait_for_selector(option_sel, state="attached", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_option_in_dropdown")
                fatal(f"'{NEW_OPTION}' option not found in select dropdown after add")
            print(f"[ok] UI: '{NEW_OPTION}' appears in select dropdown")

            snap(page, "opt_crud_04_dropdown_with_new_option")

            # Click away to close edit mode
            page.click("table thead")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 3: Remove the "blocked" option
            # ═══════════════════════════════════════════════════════════════════
            open_manage_options(page, status_col_id)
            print("[ok] re-opened ManageOptionsModal for Status")

            # Click remove button for "blocked"
            remove_btn = f'[data-testid="choice-remove-btn-{NEW_OPTION}"]'
            try:
                page.wait_for_selector(remove_btn, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_remove_btn")
                fatal(f"Remove button for '{NEW_OPTION}' not visible in modal")
            page.click(remove_btn)
            print(f"[ok] removed option '{NEW_OPTION}' in modal")

            snap(page, "opt_crud_05_after_remove_in_modal")

            # Save and wait for PATCH
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/columns/{status_col_id}" in resp.url
                    and resp.request.method == "PATCH"
                    and resp.ok
                ),
                timeout=10000,
            ):
                page.click(save_btn)
            print("[ok] Save clicked; PATCH confirmed (remove)")

            snap(page, "opt_crud_06_after_save_remove")

            # ── API pillar: verify option removed ────────────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r.status_code != 200:
                fatal(f"GET table after remove: {r.status_code} {r.text[:200]}")
            refreshed_cols = r.json()["columns"]
            updated_status = next(
                (c for c in refreshed_cols if c["column_id"] == status_col_id), None
            )
            if not updated_status:
                fatal("Status column missing from refreshed schema after remove")
            updated_choices = updated_status.get("options", {}).get("choices", [])
            updated_values = [c["value"] for c in updated_choices]
            if NEW_OPTION in updated_values:
                fatal(f"API: '{NEW_OPTION}' still in choices after remove; got {updated_values}")
            # Confirm original options (minus blocked) are intact
            for orig in original_values:
                if orig not in updated_values:
                    fatal(f"API: original option '{orig}' lost after remove; got {updated_values}")
            print(f"[ok] API: '{NEW_OPTION}' removed; remaining={updated_values}")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 4: UI verify — select dropdown no longer includes "blocked"
            # ═══════════════════════════════════════════════════════════════════
            try:
                page.wait_for_selector(cell_sel, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_select_cell_after_remove")
                fatal("select-cell not visible after remove save")

            page.click(cell_sel)

            # Option should NOT be in the dropdown
            option_locator = page.locator(f'{cell_sel} select option[value="{NEW_OPTION}"]')
            count = option_locator.count()
            if count > 0:
                snap(page, "opt_crud_FAIL_option_still_in_dropdown")
                fatal(f"'{NEW_OPTION}' still in select dropdown after remove (count={count})")
            print(f"[ok] UI: '{NEW_OPTION}' no longer in select dropdown")

            # Click away to close edit mode
            page.click("table thead")

            snap(page, "opt_crud_07_dropdown_without_removed")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 5: Kanban view — lanes reflect current options
            # ═══════════════════════════════════════════════════════════════════
            sprint_tab = '[data-testid="view-tab-Sprint Board"]'
            try:
                page.wait_for_selector(sprint_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_sprint_tab")
                fatal("Sprint Board tab not visible")
            page.click(sprint_tab)
            print("[ok] switched to Sprint Board (kanban)")

            # 'todo' lane should exist (it's an original option with a row)
            lane_todo = '[data-testid="kanban-lane-header-todo"]'
            try:
                page.wait_for_selector(lane_todo, state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_todo_lane")
                fatal("kanban-lane-header-todo not visible")
            print("[ok] Kanban: 'todo' lane visible")

            # 'blocked' lane should NOT exist
            lane_blocked = f'[data-testid="kanban-lane-header-{NEW_OPTION}"]'
            blocked_count = page.locator(lane_blocked).count()
            if blocked_count > 0:
                snap(page, "opt_crud_FAIL_blocked_lane_exists")
                fatal(f"Kanban: lane for '{NEW_OPTION}' still exists after removal")
            print(f"[ok] Kanban: no lane for '{NEW_OPTION}' (correctly removed)")

            snap(page, "opt_crud_08_kanban_no_blocked_lane")

            # ═══════════════════════════════════════════════════════════════════
            # STEP 6: Durability — navigate away and back
            # ═══════════════════════════════════════════════════════════════════
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            # Switch to Table view
            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_table_tab_after_nav")
                fatal("'Table' view tab not visible after navigation back")
            page.click(table_tab)

            try:
                page.wait_for_selector("table thead", state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_grid_after_nav")
                fatal("Table grid did not render after navigation back")

            # Verify option is still absent in dropdown after nav
            try:
                page.wait_for_selector(cell_sel, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "opt_crud_FAIL_no_cell_after_nav")
                fatal("select-cell not visible after nav back")
            page.click(cell_sel)

            option_locator_after_nav = page.locator(f'{cell_sel} select option[value="{NEW_OPTION}"]')
            count_after_nav = option_locator_after_nav.count()
            if count_after_nav > 0:
                snap(page, "opt_crud_FAIL_option_back_after_nav")
                fatal(f"'{NEW_OPTION}' reappeared in dropdown after navigation")
            print(f"[ok] UI (after nav): '{NEW_OPTION}' still absent from dropdown")

            snap(page, "opt_crud_09_after_nav_dropdown_clean")

            browser.close()

    finally:
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_column_option_add_remove ===")


if __name__ == "__main__":
    main()
