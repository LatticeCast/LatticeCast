#!/usr/bin/env python3
"""E2E test: e2e_test_column_delete — delete propagates to all views.

Topic: Deleting a column via the Table-view header menu removes it from:
  - DB schema (columns array)
  - Table view (col-header detached)
  - Kanban view (group-by option + card-field checkbox gone)
  - Timeline view (group-by option gone)
The deletion is durable across navigation.

Three pillars (developing-e2e-test):
  - Playwright UI    — verify column absent in Table, Kanban, Timeline
  - BE API verify    — GET /tables/{tid}: deleted column_id absent from columns[]
  - Durability       — navigate away and back; all three views still correct

Flow:
  setup:  login "lattice" → create workspace → create PM table (has Sprint Board
          kanban + Roadmap timeline) → add Table view → POST custom "select" column
  step 1: Table view → open col menu → click col-delete → wait for DELETE 200
  step 2: API verify — column absent from schema
  step 3: Table view — col-header detached
  step 4: Kanban view — column absent from group-by-selector options + card-field
  step 5: Timeline view — column absent from timeline-group-by-select options
  step 6: navigate away and back → re-verify all three views
  teardown: DELETE workspace

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_column_delete.py
    docker compose exec test-e2e python3 /scripts/e2e_test_column_delete.py --snapshot
"""

from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from e2e_base import BASE, BROWSER_WS, fatal, login, api, seed_login_info

ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WORKSPACE_NAME = f"e2e-col-del-{_SUFFIX}"
TABLE_ID = f"col-del-{_SUFFIX}"

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
        snap(page, "col_del_FAIL_no_view_tabs")
        fatal(f"View tabs did not load for table {table_id}")


def option_exists(page, select_testid: str, value: str) -> bool:
    """Check if a <select> with given testid contains an <option> with given value."""
    return page.locator(
        f'[data-testid="{select_testid}"] option[value="{value}"]'
    ).count() > 0


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── setup: workspace + PM table + Table view + custom select column ────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        print(f"[ok] PM table {TABLE_ID!r}")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Table", "type": "table", "config": {}})
        if r.status_code != 201:
            fatal(f"add Table view: {r.status_code} {r.text[:200]}")
        print("[ok] added 'Table' view")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "TestCol", "type": "select",
                      "options": [{"label": "Alpha"}, {"label": "Beta"}]})
        if r.status_code != 201:
            fatal(f"create TestCol column: {r.status_code} {r.text[:200]}")
        schema = r.json()
        test_col = next((c for c in schema["columns"] if c.get("name") == "TestCol"), None)
        if not test_col:
            fatal(f"TestCol missing from schema; cols={[c['name'] for c in schema['columns']]}")
        col_id = test_col["column_id"]
        print(f"[ok] TestCol (select) created → {col_id[:8]}…")

        # API pre-check
        r_pre = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
        if r_pre.status_code != 200:
            fatal(f"GET table pre-check: {r_pre.status_code}")
        pre_ids = [c["column_id"] for c in r_pre.json()["columns"]]
        if col_id not in pre_ids:
            fatal(f"TestCol {col_id[:8]}… absent from schema before test starts")

        # ── browser session ────────────────────────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.connect(BROWSER_WS)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            seed_login_info(page, token, ADMIN_USER)

            goto_table(page, ws_id, TABLE_ID)

            # Switch to Table view
            table_tab = '[data-testid="view-tab-Table"]'
            page.wait_for_selector(table_tab, state="visible", timeout=8000)
            page.click(table_tab)

            col_header_sel = f'[data-testid="col-header-{col_id}"]'
            page.wait_for_selector(col_header_sel, state="visible", timeout=15000)
            snap(page, "col_del_01_before_delete")
            print("[ok] UI pre-check: TestCol col-header visible in Table view")

            # ── step 1: open col menu → Delete ─────────────────────────────────
            col_toggle_sel = f'[data-testid="col-menu-toggle-{col_id}"]'
            page.wait_for_selector(col_toggle_sel, state="visible", timeout=8000)
            page.click(col_toggle_sel)

            delete_btn_sel = f'[data-testid="col-delete-{col_id}"]'
            page.wait_for_selector(delete_btn_sel, state="visible", timeout=5000)

            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/columns/{col_id}" in resp.url
                    and resp.request.method == "DELETE"
                    and resp.ok
                ),
                timeout=10000,
            ):
                page.click(delete_btn_sel)
            print("[ok] Delete clicked; DELETE response confirmed")
            snap(page, "col_del_02_after_delete")

            # ── step 2: API verify ─────────────────────────────────────────────
            r_post = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r_post.status_code != 200:
                fatal(f"GET table after delete: {r_post.status_code}")
            post_ids = [c["column_id"] for c in r_post.json()["columns"]]
            if col_id in post_ids:
                fatal(f"API: TestCol {col_id[:8]}… still in schema after delete!")
            print("[ok] API: TestCol absent from schema")

            # ── step 3: Table view — col-header detached ───────────────────────
            page.wait_for_selector(col_header_sel, state="detached", timeout=8000)
            print("[ok] Table view: col-header detached")
            snap(page, "col_del_03_table_gone")

            # ── step 4: Kanban view — group-by + card-field gone ───────────────
            kanban_tab = '[data-testid="view-tab-Sprint Board"]'
            page.wait_for_selector(kanban_tab, state="visible", timeout=8000)
            page.click(kanban_tab)

            # Wait for kanban to render (group-by-selector is always visible)
            page.wait_for_selector('[data-testid="group-by-selector"]', state="visible", timeout=10000)

            if option_exists(page, "group-by-selector", col_id):
                snap(page, "col_del_FAIL_kanban_groupby")
                fatal(f"Kanban: TestCol still in group-by-selector options after delete!")
            print("[ok] Kanban: TestCol absent from group-by-selector")

            # Open card-fields panel and verify checkbox gone
            page.click('[data-testid="kanban-card-fields-btn"]')
            card_field_sel = f'[data-testid="kanban-card-field-{col_id}-checkbox"]'
            if page.locator(card_field_sel).count() > 0:
                snap(page, "col_del_FAIL_kanban_cardfield")
                fatal(f"Kanban: TestCol card-field checkbox still present after delete!")
            print("[ok] Kanban: TestCol absent from card-field checkboxes")
            snap(page, "col_del_04_kanban_gone")

            # ── step 5: Timeline view — group-by option gone ───────────────────
            timeline_tab = '[data-testid="view-tab-Roadmap"]'
            page.wait_for_selector(timeline_tab, state="visible", timeout=8000)
            page.click(timeline_tab)

            page.wait_for_selector(
                '[data-testid="timeline-group-by-select"]', state="visible", timeout=10000
            )

            if option_exists(page, "timeline-group-by-select", col_id):
                snap(page, "col_del_FAIL_timeline_groupby")
                fatal(f"Timeline: TestCol still in group-by-select options after delete!")
            print("[ok] Timeline: TestCol absent from timeline-group-by-select")
            snap(page, "col_del_05_timeline_gone")

            # ── step 6: durability — navigate away and back ────────────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            # Table view durability
            page.wait_for_selector(table_tab, state="visible", timeout=8000)
            page.click(table_tab)
            page.wait_for_selector("table thead", state="visible", timeout=15000)

            r_dur = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            dur_ids = [c["column_id"] for c in r_dur.json()["columns"]]
            if col_id in dur_ids:
                fatal(f"Durability API: TestCol reappeared!")
            if page.query_selector(col_header_sel) is not None:
                fatal(f"Durability Table UI: col-header reappeared!")
            print("[ok] Durability: Table view correct after nav")

            # Kanban durability
            page.click(kanban_tab)
            page.wait_for_selector('[data-testid="group-by-selector"]', state="visible", timeout=10000)
            if option_exists(page, "group-by-selector", col_id):
                fatal(f"Durability Kanban: TestCol reappeared in group-by-selector!")
            print("[ok] Durability: Kanban view correct after nav")

            # Timeline durability
            page.click(timeline_tab)
            page.wait_for_selector(
                '[data-testid="timeline-group-by-select"]', state="visible", timeout=10000
            )
            if option_exists(page, "timeline-group-by-select", col_id):
                fatal(f"Durability Timeline: TestCol reappeared in group-by-select!")
            print("[ok] Durability: Timeline view correct after nav")

            snap(page, "col_del_06_durability_done")
            browser.close()

    finally:
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_column_delete ===")


if __name__ == "__main__":
    main()
