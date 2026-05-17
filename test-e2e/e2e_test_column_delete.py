#!/usr/bin/env python3
"""E2E test: e2e_test_column_delete — delete propagates.

Topic: Deleting a column via the column-header menu removes it from the DB
schema (columns array) and from the Table-view header row immediately; the
deletion survives navigation away-and-back (durable propagation).

Three pillars (developing-e2e-test):
  - Playwright UI    — col-menu-toggle → col-delete-{id} → col-header detached
  - BE API verify    — GET /tables/{tid}: deleted column_id absent from columns[]
  - Durability       — navigate away and back; column absent in API + UI

Flow:
  setup:  login "lattice" → create workspace → create PM table → add Table view
          → POST /columns "Notes" (text) → POST /rows with Notes="hello"
  step 1: Table view → wait for col-header-{notes_col_id}
          → open Notes col menu → click col-delete-{notes_col_id}
          → wait for DELETE /columns/{cid} 200 response
  step 2: API verify — GET /tables/{tid}: Notes column absent from columns[]
  step 3: UI verify — col-header-{notes_col_id} detached from DOM
  step 4: navigate away and back → API + UI verify still absent
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


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create workspace ────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── 2. Create PM table ─────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        print(f"[ok] PM table {TABLE_ID!r}")

        # ── 3. Add a Table view (PM template only creates kanban + timeline) ──
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Table", "type": "table", "config": {}})
        if r.status_code != 201:
            fatal(f"add Table view: {r.status_code} {r.text[:200]}")
        print("[ok] added 'Table' view")

        # ── 4. Add a custom 'Notes' text column ───────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Notes", "type": "text"})
        if r.status_code != 201:
            fatal(f"create Notes column: {r.status_code} {r.text[:200]}")
        schema = r.json()
        notes_col = next((c for c in schema["columns"] if c.get("name") == "Notes"), None)
        if not notes_col:
            fatal(f"Notes column missing from schema; cols={[c['name'] for c in schema['columns']]}")
        notes_col_id = notes_col["column_id"]
        print(f"[ok] Notes column created → {notes_col_id[:8]}…")

        # API pre-check: column is in schema
        r_pre = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
        if r_pre.status_code != 200:
            fatal(f"GET table pre-check: {r_pre.status_code}")
        pre_ids = [c["column_id"] for c in r_pre.json()["columns"]]
        if notes_col_id not in pre_ids:
            fatal(f"Notes column {notes_col_id[:8]}… absent from schema before test starts")
        print("[ok] API pre-check: Notes column present in schema")

        # ── 5. Add a row with Notes="hello" ───────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {notes_col_id: "hello"}})
        if r.status_code != 201:
            fatal(f"add row: {r.status_code} {r.text[:200]}")
        print("[ok] row added with Notes='hello'")

        # ── 6. Browser session ─────────────────────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.connect(BROWSER_WS)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            seed_login_info(page, token, ADMIN_USER)

            goto_table(page, ws_id, TABLE_ID)

            # Switch to the Table view
            table_tab = '[data-testid="view-tab-Table"]'
            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_table_tab")
                fatal("'Table' view tab not visible")
            page.click(table_tab)

            # UI pre-check: Notes col-header must be visible before delete
            col_header_sel = f'[data-testid="col-header-{notes_col_id}"]'
            try:
                page.wait_for_selector(col_header_sel, state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_col_header")
                fatal(f"col-header-{notes_col_id[:8]}… not visible — testid missing from <th>?")

            snap(page, "col_del_01_before_delete")
            print("[ok] UI pre-check: Notes col-header visible in Table view")

            # ── step 1: open column menu → click Delete ────────────────────────
            col_toggle_sel = f'[data-testid="col-menu-toggle-{notes_col_id}"]'
            try:
                page.wait_for_selector(col_toggle_sel, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_col_toggle")
                fatal(f"col-menu-toggle-{notes_col_id[:8]}… not visible")
            page.click(col_toggle_sel)

            delete_btn_sel = f'[data-testid="col-delete-{notes_col_id}"]'
            try:
                page.wait_for_selector(delete_btn_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_delete_btn")
                fatal(f"col-delete-{notes_col_id[:8]}… not visible — data-testid missing from Delete button?")

            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/columns/{notes_col_id}" in resp.url
                    and resp.request.method == "DELETE"
                    and resp.ok
                ),
                timeout=10000,
            ):
                page.click(delete_btn_sel)
            print("[ok] Delete clicked; DELETE /columns/{…} response confirmed")

            snap(page, "col_del_02_after_delete_click")

            # ── step 2: API verify — column absent from schema ─────────────────
            r_post = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r_post.status_code != 200:
                fatal(f"GET table after delete: {r_post.status_code} {r_post.text[:200]}")
            post_ids = [c["column_id"] for c in r_post.json()["columns"]]
            if notes_col_id in post_ids:
                fatal(f"API: Notes column {notes_col_id[:8]}… still in schema after delete!")
            print("[ok] API: Notes column absent from schema after delete")

            # ── step 3: UI verify — col-header detached from DOM ──────────────
            try:
                page.wait_for_selector(col_header_sel, state="detached", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_header_still_in_dom")
                fatal(f"col-header-{notes_col_id[:8]}… still in DOM after DELETE confirmed")
            print("[ok] UI: Notes col-header detached from Table view DOM")

            snap(page, "col_del_03_header_gone")

            # ── step 4: navigate away and back; verify durability ─────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_table_tab_after_nav")
                fatal("'Table' view tab not visible after navigation back")
            page.click(table_tab)

            # Wait for grid to fully render before negative assertion
            try:
                page.wait_for_selector("table thead", state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "col_del_FAIL_no_thead_after_nav")
                fatal("Table grid <thead> did not render after navigation back")

            # API durability
            r_dur = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r_dur.status_code != 200:
                fatal(f"GET table durability check: {r_dur.status_code}")
            dur_ids = [c["column_id"] for c in r_dur.json()["columns"]]
            if notes_col_id in dur_ids:
                fatal(f"API durability: Notes column {notes_col_id[:8]}… reappeared after navigation!")
            print("[ok] API durability: Notes column still absent after nav")

            # UI durability
            if page.query_selector(col_header_sel) is not None:
                snap(page, "col_del_FAIL_header_reappeared")
                fatal(f"UI durability: col-header-{notes_col_id[:8]}… reappeared after navigation!")
            print("[ok] UI durability: Notes col-header still absent after nav")

            snap(page, "col_del_04_after_nav")
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
