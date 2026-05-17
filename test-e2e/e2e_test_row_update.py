"""E2E test: edit cell → DB — various column types.

Scenario:
  1. Create workspace + table with text, select, checkbox, date columns.
  2. Create a row with initial values via API.
  3. Edit text cell via UI (click → input → Enter) → verify DB.
  4. Edit select cell via UI (click → dropdown change) → verify DB.
  5. Toggle checkbox cell via UI (click button) → verify DB.
  6. Edit date cell via UI (click → input → Enter) → verify DB.
  7. Reload page → verify all edits persisted in UI.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_row_update.py [--snapshot]
"""

from __future__ import annotations

import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time()) % 100000
WORKSPACE_NAME = f"row-update-{_TS}"
TABLE_ID = f"row-update-{_TS}"

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
    return r.json()["access_token"]


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def get_row_from_api(token: str, table_id: str, row_id: int) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    if r.status_code != 200:
        fatal(f"GET row {row_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def get_cell_locator(page, row_id: int, col_index: int):
    row = page.locator(f'[data-testid="grid-row-{row_id}"]')
    return row.locator(f"td:nth-child({col_index + 2})")


def wait_table_page(page, ws_name: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        fatal(f"Table page did not finish loading for {table_id!r}")


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: workspace ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    try:
        # ── Setup: table ─────────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        print(f"[setup] table {TABLE_ID!r}")

        # ── Setup: columns ───────────────────────────────────────────────────
        col_defs = [
            ("Name", "text", None),
            ("Status", "select", {"choices": [
                {"value": "todo", "color": ""},
                {"value": "in_progress", "color": ""},
                {"value": "done", "color": ""},
            ]}),
            ("Done", "checkbox", None),
            ("Due", "date", None),
        ]
        col_ids = {}
        for name, ctype, options in col_defs:
            payload: dict = {"name": name, "type": ctype}
            if options:
                payload["options"] = options
            r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token, json=payload)
            if r.status_code not in (200, 201):
                fatal(f"create column {name!r}: {r.status_code} {r.text[:200]}")
            schema = r.json()
            col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
            if not col:
                fatal(f"column {name!r} not found in schema response")
            col_ids[name] = col["column_id"]
            print(f"[setup] column {name!r} ({ctype}) → {col_ids[name]}")

        # ── Setup: create row with initial data ──────────────────────────────
        initial_data = {
            col_ids["Name"]: "Alice",
            col_ids["Status"]: "todo",
            col_ids["Done"]: False,
            col_ids["Due"]: "2026-01-01",
        }
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token, json={"row_data": initial_data})
        if r.status_code != 201:
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[setup] row → id={row_id}")

        # ── Determine column order in grid ───────────────────────────────────
        r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
        if r.status_code != 200:
            fatal(f"get table schema: {r.status_code} {r.text[:200]}")
        columns = r.json().get("columns", [])
        col_order = [c["column_id"] for c in columns]
        idx_name = col_order.index(col_ids["Name"])
        idx_status = col_order.index(col_ids["Status"])
        idx_done = col_order.index(col_ids["Done"])
        idx_due = col_order.index(col_ids["Due"])
        print(f"[setup] col indices: Name={idx_name}, Status={idx_status}, Done={idx_done}, Due={idx_due}")

        # ── Playwright session ───────────────────────────────────────────────
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

            # ── Navigate to table ────────────────────────────────────────────
            wait_table_page(page, ws_name, TABLE_ID)

            try:
                page.wait_for_selector(f'[data-testid="grid-row-{row_id}"]', timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_no_row")
                fatal("Row not visible after page load")

            snap(page, "row_update_01_initial")
            print("[ok] table loaded with row visible")

            # ── Test 1: Edit text cell (Name: Alice → Bob) ───────────────────
            cell_name = get_cell_locator(page, row_id, idx_name)
            cell_name.click()

            input_loc = cell_name.locator("input")
            try:
                input_loc.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_text_no_input")
                fatal("Edit input did not appear after clicking text cell")

            input_loc.fill("Bob")
            with page.expect_response(
                lambda resp: "/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                input_loc.press("Enter")

            snap(page, "row_update_02_text_committed")

            row_api = get_row_from_api(token, TABLE_ID, row_id)
            db_name = row_api["row_data"].get(col_ids["Name"])
            if db_name != "Bob":
                fatal(f"Text edit DB verify failed: expected 'Bob', got {db_name!r}")
            print("[ok] text cell: Alice → Bob (DB verified)")

            # ── Test 2: Edit select cell (Status: todo → done) ───────────────
            cell_status = get_cell_locator(page, row_id, idx_status)
            cell_status.click()

            select_loc = cell_status.locator("select")
            try:
                select_loc.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_select_no_dropdown")
                fatal("Select dropdown did not appear after clicking select cell")

            with page.expect_response(
                lambda resp: "/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                select_loc.select_option("done")

            snap(page, "row_update_03_select_committed")

            row_api = get_row_from_api(token, TABLE_ID, row_id)
            db_status = row_api["row_data"].get(col_ids["Status"])
            if db_status != "done":
                fatal(f"Select edit DB verify failed: expected 'done', got {db_status!r}")
            print("[ok] select cell: todo → done (DB verified)")

            # ── Test 3: Toggle checkbox (Done: false → true) ─────────────────
            checkbox_btn = page.locator(
                f'[data-testid="checkbox-cell-{row_id}-{col_ids["Done"]}"]'
            )
            try:
                checkbox_btn.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_no_checkbox")
                fatal("Checkbox button not visible")

            with page.expect_response(
                lambda resp: "/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                checkbox_btn.click()

            snap(page, "row_update_04_checkbox_toggled")

            row_api = get_row_from_api(token, TABLE_ID, row_id)
            db_done = row_api["row_data"].get(col_ids["Done"])
            if db_done is not True:
                fatal(f"Checkbox toggle DB verify failed: expected True, got {db_done!r}")
            print("[ok] checkbox cell: false → true (DB verified)")

            # ── Test 4: Edit date cell (Due: 2026-01-01 → 2026-12-31) ────────
            cell_due = get_cell_locator(page, row_id, idx_due)
            cell_due.click()

            date_input = cell_due.locator("input[type='date']")
            try:
                date_input.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_date_no_input")
                fatal("Date input did not appear after clicking date cell")

            date_input.fill("2026-12-31")
            with page.expect_response(
                lambda resp: "/rows/" in resp.url and resp.request.method == "PUT",
                timeout=10000,
            ):
                date_input.press("Enter")

            snap(page, "row_update_05_date_committed")

            row_api = get_row_from_api(token, TABLE_ID, row_id)
            db_due = row_api["row_data"].get(col_ids["Due"])
            if db_due != "2026-12-31":
                fatal(f"Date edit DB verify failed: expected '2026-12-31', got {db_due!r}")
            print("[ok] date cell: 2026-01-01 → 2026-12-31 (DB verified)")

            # ── Test 5: Reload → verify all edits persist in UI ──────────────
            wait_table_page(page, ws_name, TABLE_ID)

            try:
                page.wait_for_selector(f'[data-testid="grid-row-{row_id}"]', timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_update_FAIL_reload")
                fatal("Row not visible after reload")

            snap(page, "row_update_06_after_reload")

            # Verify text cell shows "Bob"
            cell_name = get_cell_locator(page, row_id, idx_name)
            name_text = cell_name.inner_text()
            if "Bob" not in name_text:
                fatal(f"After reload: Name not showing 'Bob', got {name_text!r}")

            # Verify select cell shows "done"
            cell_status = get_cell_locator(page, row_id, idx_status)
            status_text = cell_status.inner_text()
            if "done" not in status_text:
                fatal(f"After reload: Status not showing 'done', got {status_text!r}")

            # Verify checkbox is checked (aria-checked="true")
            checkbox_btn = page.locator(
                f'[data-testid="checkbox-cell-{row_id}-{col_ids["Done"]}"]'
            )
            aria = checkbox_btn.get_attribute("aria-checked")
            if aria != "true":
                fatal(f"After reload: Checkbox aria-checked={aria!r}, expected 'true'")

            # Verify date cell shows "2026-12-31"
            cell_due = get_cell_locator(page, row_id, idx_due)
            due_text = cell_due.inner_text()
            if "2026-12-31" not in due_text:
                fatal(f"After reload: Due not showing '2026-12-31', got {due_text!r}")

            print("[ok] all edits persist after reload")

            browser.close()

    finally:
        # ── Teardown ─────────────────────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_uuid}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_row_update ===")


if __name__ == "__main__":
    main()
