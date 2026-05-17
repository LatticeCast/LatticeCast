"""E2E test: e2e_test_column_checkbox_type — checkbox toggle.

Topic: A checkbox column cell renders as a toggle switch, clicking it
flips the value (false→true, true→false), the new state is persisted
to the DB via the BE API, and survives navigation.

Three pillars (developing-e2e-test):
  - Playwright UI    — checkbox button renders with correct aria-checked
                       state, clicking toggles it
  - BE API verify    — GET /rows/{row_id} confirms stored boolean value
  - Durability check — navigate away and back; toggled state persists

Flow:
  setup:  login as "lattice" → create workspace → create blank table
          → add a checkbox column "Done" → create a table view
          → create one row with checkbox=false
  step 1: navigate to table, click Table view tab, wait for grid
  step 2: API pillar — GET /rows/{row_id} confirms initial value (false)
  step 3: UI pillar  — checkbox-cell renders with aria-checked="false"
  step 4: Click checkbox → UI shows aria-checked="true"
  step 5: API pillar — GET /rows/{row_id} confirms value flipped to true
  step 6: Click again → UI shows aria-checked="false"
  step 7: API pillar — GET /rows/{row_id} confirms value back to false
  step 8: Toggle back to true, navigate away and back → still true
  teardown: DELETE workspace

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_column_checkbox_type.py
    docker compose exec test-e2e python3 /scripts/e2e_test_column_checkbox_type.py --snapshot
"""

from __future__ import annotations

import sys
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from e2e_base import BASE, BROWSER_WS, api, fatal, login, seed_login_info

ADMIN_USER = "lattice"
_TS = int(time.time()) % 100000
WS_NAME = f"e2e-chk-{_TS}"
TABLE_ID = f"chk-{_TS}"
COL_NAME = "Done"

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
        snap(page, "chk_FAIL_table_not_loaded")
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

        # ── 3. Add checkbox column ─────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": COL_NAME, "type": "checkbox"})
        if r.status_code != 201:
            fatal(f"add checkbox column: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col = next((c for c in schema["columns"] if c["name"] == COL_NAME), None)
        if col is None:
            fatal(f"column {COL_NAME!r} missing after create; got {[c['name'] for c in schema['columns']]}")
        col_id = col["column_id"]
        print(f"[ok] checkbox column {COL_NAME!r} → {col_id[:8]}…")

        # ── 4. Create table view ───────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Table", "type": "table", "config": {}})
        if r.status_code not in (200, 201):
            fatal(f"create table view: {r.status_code} {r.text[:200]}")
        print("[ok] table view created")

        # ── 5. Create row with checkbox=false ──────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {col_id: False}})
        if r.status_code not in (200, 201):
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row = r.json()
        row_id = row["row_id"]
        print(f"[ok] row id={row_id} checkbox=false")

        # ── 6. API pillar: verify initial value (false) ────────────────────────
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
        if r.status_code != 200:
            fatal(f"GET row: {r.status_code} {r.text[:200]}")
        stored = r.json()["row_data"].get(col_id)
        if stored is not False:
            fatal(f"API: initial checkbox={stored!r}, expected False")
        print("[ok] API: initial checkbox=False confirmed")

        # ── 7. Browser session ─────────────────────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.connect(BROWSER_WS)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            seed_login_info(page, token, ADMIN_USER)

            goto_table(page, ws_name, TABLE_ID)
            snap(page, "chk_01_initial")

            # Click Table view tab
            table_tab = '[data-testid="view-tab-Table"]'
            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "chk_FAIL_no_table_tab")
                fatal("'Table' view tab not visible")
            page.click(table_tab)

            # ── step 3: UI — checkbox renders with aria-checked=false ──────────
            chk_sel = f'[data-testid="checkbox-cell-{row_id}-{col_id}"]'
            try:
                page.wait_for_selector(chk_sel, state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "chk_FAIL_no_checkbox_cell")
                fatal(
                    f"checkbox-cell-{row_id}-{col_id[:8]}… not visible — "
                    "missing data-testid on checkbox button in TableGrid?"
                )

            aria = page.get_attribute(chk_sel, "aria-checked")
            if aria != "false":
                snap(page, "chk_FAIL_initial_aria")
                fatal(f"UI: initial aria-checked={aria!r}, expected 'false'")
            print("[ok] UI: checkbox aria-checked='false' (initial)")
            snap(page, "chk_02_initial_false")

            # ── step 4: Click checkbox → toggles to true ───────────────────────
            with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
                page.click(chk_sel)
            resp_info.value

            # Wait for UI to update
            page.wait_for_function(
                f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "true"',
                timeout=5000,
            )
            aria = page.get_attribute(chk_sel, "aria-checked")
            if aria != "true":
                snap(page, "chk_FAIL_toggle_true")
                fatal(f"UI: after click aria-checked={aria!r}, expected 'true'")
            print("[ok] UI: checkbox toggled to aria-checked='true'")
            snap(page, "chk_03_toggled_true")

            # ── step 5: API pillar — verify toggled to true ────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after toggle: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id)
            if stored is not True:
                fatal(f"API: after toggle checkbox={stored!r}, expected True")
            print("[ok] API: checkbox=True confirmed after toggle")

            # ── step 6: Click again → toggles back to false ────────────────────
            with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
                page.click(chk_sel)
            resp_info.value

            page.wait_for_function(
                f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "false"',
                timeout=5000,
            )
            aria = page.get_attribute(chk_sel, "aria-checked")
            if aria != "false":
                snap(page, "chk_FAIL_toggle_false")
                fatal(f"UI: after 2nd click aria-checked={aria!r}, expected 'false'")
            print("[ok] UI: checkbox toggled back to aria-checked='false'")
            snap(page, "chk_04_toggled_false")

            # ── step 7: API pillar — verify back to false ──────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after 2nd toggle: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id)
            if stored is not False:
                fatal(f"API: after 2nd toggle checkbox={stored!r}, expected False")
            print("[ok] API: checkbox=False confirmed after 2nd toggle")

            # ── step 8: Durability — toggle to true, navigate away and back ────
            with page.expect_response(lambda r: "/api/v1/tables/" in r.url and r.request.method == "PUT") as resp_info:
                page.click(chk_sel)
            resp_info.value

            page.wait_for_function(
                f'document.querySelector(\'{chk_sel}\')?.getAttribute("aria-checked") === "true"',
                timeout=5000,
            )
            print("[ok] UI: checkbox set to true for durability check")

            page.goto(f"{BASE}/{ws_name}", wait_until="domcontentloaded")
            goto_table(page, ws_name, TABLE_ID)

            try:
                page.wait_for_selector(table_tab, state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "chk_FAIL_no_table_tab_after_nav")
                fatal("'Table' view tab not visible after navigation back")
            page.click(table_tab)

            try:
                page.wait_for_selector(chk_sel, state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "chk_FAIL_no_checkbox_after_nav")
                fatal(f"checkbox-cell not visible after navigation back")

            aria = page.get_attribute(chk_sel, "aria-checked")
            if aria != "true":
                snap(page, "chk_FAIL_durability")
                fatal(f"Durability: aria-checked={aria!r} after nav, expected 'true'")
            print("[ok] Durability: checkbox still true after navigation")

            # API confirm durability
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row durability: {r.status_code} {r.text[:200]}")
            stored = r.json()["row_data"].get(col_id)
            if stored is not True:
                fatal(f"API durability: checkbox={stored!r}, expected True")
            print("[ok] API: durability confirmed checkbox=True")

            snap(page, "chk_05_durability_pass")

            browser.close()

    finally:
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_column_checkbox_type ===")


if __name__ == "__main__":
    main()
