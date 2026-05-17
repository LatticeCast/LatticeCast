#!/usr/bin/env python3
"""E2E test: e2e_test_column_tags_type — tags add/remove.

Topic: A tags column cell allows adding tags from the available choices via
a "+" popup and removing them via the "×" button on each pill. Changes are
persisted to the DB and survive navigation.

Three pillars (developing-e2e-test):
  - Playwright UI    — tag pills render, add/remove buttons work
  - BE API verify    — GET /rows/{row_id} confirms stored array values
  - Durability check — navigate away and back; tags persist

Flow:
  setup:  login as "lattice" → create workspace → create blank table
          → add a tags column "Labels" with choices [bug, feature, docs]
          → create a table view → create one row with tags=[]
  step 1: navigate to table, click Table view tab, wait for grid
  step 2: API pillar — GET /rows/{row_id} confirms initial empty tags
  step 3: UI pillar  — tags cell renders empty, "+" button visible
  step 4: Click "+" → popup appears with 3 choices
  step 5: Click "bug" choice → tag pill "bug" appears in cell
  step 6: API pillar — GET /rows/{row_id} confirms ["bug"]
  step 7: Add "feature" tag via "+" popup
  step 8: API pillar — confirms ["bug", "feature"]
  step 9: Remove "bug" via × button → pill disappears
  step 10: API pillar — confirms ["feature"]
  step 11: Durability — navigate away and back → "feature" still present
  teardown: DELETE workspace

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_column_tags_type.py
    docker compose exec test-e2e python3 /scripts/e2e_test_column_tags_type.py --snapshot
"""

from __future__ import annotations

import sys
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from e2e_base import BASE, BROWSER_WS, api, fatal, login, seed_login_info

ADMIN_USER = "lattice"
_TS = int(time.time()) % 100000
WS_NAME = f"e2e-tags-{_TS}"
TABLE_ID = f"tags-{_TS}"
COL_NAME = "Labels"
TAG_CHOICES = [
    {"value": "bug", "color": "#ef4444"},
    {"value": "feature", "color": "#3b82f6"},
    {"value": "docs", "color": "#10b981"},
]

SNAPSHOT = "--snapshot" in sys.argv


def snap(page, name: str) -> None:
    if SNAPSHOT:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_name: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-table-loaded="true"]', state="attached", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "tags_FAIL_table_not_loaded")
        fatal(f"Table {table_id!r} did not finish loading")


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create workspace ────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_id = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[ok] workspace {WS_NAME!r} → {ws_id}")

    try:
        # ── 2. Create blank table ──────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_name})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        print(f"[ok] table {TABLE_ID!r} (cols={len(schema['columns'])})")

        # ── 3. Add tags column ─────────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": COL_NAME, "type": "tags", "options": {"choices": TAG_CHOICES}})
        if r.status_code != 201:
            fatal(f"add tags column: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col = next((c for c in schema["columns"] if c["name"] == COL_NAME), None)
        if col is None:
            fatal(f"column {COL_NAME!r} missing after create; got {[c['name'] for c in schema['columns']]}")
        col_id = col["column_id"]
        print(f"[ok] tags column {COL_NAME!r} → {col_id[:8]}…")

        # ── 4. Create table view ───────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Table", "type": "table", "config": {}})
        if r.status_code not in (200, 201):
            fatal(f"create table view: {r.status_code} {r.text[:200]}")
        print("[ok] table view created")

        # ── 5. Create row with empty tags ──────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {col_id: []}})
        if r.status_code not in (200, 201):
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row = r.json()
        row_id = row["row_id"]
        print(f"[ok] row id={row_id} tags=[]")

        # ── 6. API pillar: verify initial value (empty array) ──────────────────
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
        if r.status_code != 200:
            fatal(f"GET row: {r.status_code} {r.text[:200]}")
        stored = r.json()["row_data"].get(col_id, [])
        if stored != []:
            fatal(f"API: initial tags={stored!r}, expected []")
        print("[ok] API: initial tags=[] confirmed")

        # ── 7. Browser session ─────────────────────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.connect(BROWSER_WS)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            seed_login_info(page, token, ADMIN_USER)

            goto_table(page, ws_name, TABLE_ID)
            snap(page, "tags_01_initial")

            # Click Table view tab
            table_tab = '[data-testid="view-tab-Table"]'
            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_table_tab")
                fatal("'Table' view tab not visible")
            page.click(table_tab)

            # Wait for the grid to render
            try:
                page.wait_for_selector("table thead", state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_grid")
                fatal("Table grid did not render")

            # ── step 3: UI — tags cell renders, "+" button visible ─────────────
            cell_sel = f'[data-testid="tags-cell-{row_id}-{col_id}"]'
            add_btn_sel = f'[data-testid="tags-add-btn-{row_id}-{col_id}"]'
            try:
                page.wait_for_selector(cell_sel, state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_cell")
                fatal(f"tags-cell-{row_id}-{col_id[:8]}… not visible")

            add_btn = page.locator(add_btn_sel)
            if not add_btn.is_visible():
                snap(page, "tags_FAIL_no_add_btn")
                fatal("tags add (+) button not visible on empty cell")
            print("[ok] UI: tags cell rendered, '+' button visible")
            snap(page, "tags_02_empty_cell")

            # ── step 4: Click "+" → popup appears ──────────────────────────────
            popup_sel = f'[data-testid="tags-popup-{row_id}-{col_id}"]'
            page.click(add_btn_sel)
            try:
                page.wait_for_selector(popup_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_popup")
                fatal("Tags popup did not appear after clicking '+'")
            print("[ok] UI: tags popup opened")
            snap(page, "tags_03_popup_open")

            # ── step 5: Click "bug" choice → tag pill appears ──────────────────
            choice_bug_sel = f'[data-testid="tags-choice-{row_id}-{col_id}-bug"]'
            try:
                page.wait_for_selector(choice_bug_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_bug_choice")
                fatal("'bug' choice not visible in tags popup")

            with page.expect_response(
                lambda resp: f"/api/v1/tables/{TABLE_ID}/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                page.click(choice_bug_sel)
            print("[ok] UI: clicked 'bug' choice; PUT confirmed")

            # Verify pill appeared
            pill_bug_sel = f'[data-testid="tag-pill-{row_id}-{col_id}-bug"]'
            try:
                page.wait_for_selector(pill_bug_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_bug_pill")
                fatal("'bug' tag pill did not appear after adding")
            print("[ok] UI: 'bug' pill visible")
            snap(page, "tags_04_bug_added")

            # ── step 6: API pillar — verify ["bug"] ────────────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after add bug: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id, [])
            if stored != ["bug"]:
                fatal(f"API: after add 'bug' tags={stored!r}, expected ['bug']")
            print("[ok] API: tags=['bug'] confirmed")

            # ── step 7: Add "feature" tag ──────────────────────────────────────
            # Re-open popup (it closes after adding a tag per store logic)
            page.click(add_btn_sel)
            try:
                page.wait_for_selector(popup_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_popup_2nd")
                fatal("Tags popup did not reopen for second add")

            choice_feat_sel = f'[data-testid="tags-choice-{row_id}-{col_id}-feature"]'
            try:
                page.wait_for_selector(choice_feat_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_feature_choice")
                fatal("'feature' choice not visible in tags popup")

            with page.expect_response(
                lambda resp: f"/api/v1/tables/{TABLE_ID}/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                page.click(choice_feat_sel)
            print("[ok] UI: clicked 'feature' choice; PUT confirmed")

            pill_feat_sel = f'[data-testid="tag-pill-{row_id}-{col_id}-feature"]'
            try:
                page.wait_for_selector(pill_feat_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_feature_pill")
                fatal("'feature' tag pill did not appear after adding")
            print("[ok] UI: 'feature' pill visible")
            snap(page, "tags_05_feature_added")

            # ── step 8: API pillar — verify ["bug", "feature"] ─────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after add feature: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id, [])
            if set(stored) != {"bug", "feature"}:
                fatal(f"API: after add 'feature' tags={stored!r}, expected ['bug', 'feature']")
            print(f"[ok] API: tags={stored!r} confirmed")

            # ── step 9: Remove "bug" via × button ──────────────────────────────
            remove_bug_sel = f'[data-testid="tag-remove-{row_id}-{col_id}-bug"]'
            try:
                page.wait_for_selector(remove_bug_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_remove_btn")
                fatal("'bug' remove (×) button not visible")

            with page.expect_response(
                lambda resp: f"/api/v1/tables/{TABLE_ID}/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                page.click(remove_bug_sel)
            print("[ok] UI: clicked remove for 'bug'; PUT confirmed")

            # Verify 'bug' pill is gone
            try:
                page.wait_for_selector(pill_bug_sel, state="detached", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_bug_still_visible")
                fatal("'bug' pill still visible after removal")
            print("[ok] UI: 'bug' pill removed")
            snap(page, "tags_06_bug_removed")

            # ── step 10: API pillar — verify ["feature"] ───────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after remove bug: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id, [])
            if stored != ["feature"]:
                fatal(f"API: after remove 'bug' tags={stored!r}, expected ['feature']")
            print("[ok] API: tags=['feature'] confirmed")

            # ── step 11: Durability — navigate away and back ───────────────────
            page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded")
            goto_table(page, ws_name, TABLE_ID)

            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_table_tab_after_nav")
                fatal("'Table' view tab not visible after navigation back")
            page.click(table_tab)

            try:
                page.wait_for_selector(pill_feat_sel, state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "tags_FAIL_no_feature_after_nav")
                fatal("'feature' pill not visible after navigation back")
            print("[ok] Durability: 'feature' pill still visible after nav")

            # API confirm durability
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row durability: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id, [])
            if stored != ["feature"]:
                fatal(f"API durability: tags={stored!r}, expected ['feature']")
            print("[ok] API: durability confirmed tags=['feature']")

            # Verify 'bug' is NOT present (removal persisted)
            pill_bug_after = page.locator(pill_bug_sel)
            if pill_bug_after.count() > 0:
                snap(page, "tags_FAIL_bug_returned")
                fatal("'bug' pill reappeared after navigation — removal not durable")
            print("[ok] Durability: 'bug' pill still removed after nav")

            snap(page, "tags_07_durability_pass")

            browser.close()

    finally:
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_column_tags_type ===")


if __name__ == "__main__":
    main()
