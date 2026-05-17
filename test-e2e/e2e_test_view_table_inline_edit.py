"""E2E test: inline cell edit — click cell, type value, commit, verify DB.

Scenario:
  1. Create workspace + table + 2 text columns (Name, City) + 1 number column (Score).
  2. Create 2 rows: ("Alice","Tokyo",100), ("Bob","Berlin",200)
  3. Navigate to table page.
  4. Double-click (click) a text cell → input appears → type new value → press Enter.
  5. Verify the row was updated via GET API (DB roundtrip).
  6. Edit a number cell the same way.
  7. Edit a cell and press Escape → verify no change persisted.
  8. Edit a cell and blur (click away) → verify change persisted (blur commits).

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_inline_edit.py [--snapshot]
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
WORKSPACE_NAME = f"inline-edit-{_TS}"
TABLE_ID = f"inline-edit-{_TS}"

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


def get_row_from_api(token: str, table_id: str, row_id: int) -> dict:
    """Fetch a single row from the API to verify DB state."""
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    if r.status_code != 200:
        fatal(f"GET row {row_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def get_cell_locator(page, row_id: int, col_index: int):
    """Get a locator for the nth data cell (0-based) in a grid row.

    Layout: td[0]=row-number (sticky), td[1..N]=data columns in order.
    So col_index 0 → td:nth-child(2).
    """
    row = page.locator(f'[data-testid="grid-row-{row_id}"]')
    return row.locator(f"td:nth-child({col_index + 2})")


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

    # ── Setup: columns (Name text, City text, Score number) ──────────────────
    col_ids = {}
    col_types = {"Name": "text", "City": "text", "Score": "number"}
    for name, ctype in col_types.items():
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": name, "type": ctype})
        if r.status_code not in (200, 201):
            fatal(f"create column {name!r}: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        if not col:
            fatal(f"column {name!r} not found in schema")
        col_ids[name] = col["column_id"]
        print(f"[setup] column {name!r} ({ctype}) → {col_ids[name]}")

    col_name = col_ids["Name"]
    col_city = col_ids["City"]
    col_score = col_ids["Score"]

    # ── Setup: 2 rows ────────────────────────────────────────────────────────
    rows_data = [
        {"Name": "Alice", "City": "Tokyo", "Score": 100},
        {"Name": "Bob", "City": "Berlin", "Score": 200},
    ]
    row_ids: list[int] = []
    for rd in rows_data:
        row_data = {col_name: rd["Name"], col_city: rd["City"], col_score: rd["Score"]}
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": row_data})
        if r.status_code != 201:
            fatal(f"create row {rd!r}: {r.status_code} {r.text[:200]}")
        row_ids.append(r.json()["row_id"])
    print(f"[setup] rows: {row_ids}")

    rid_alice, rid_bob = row_ids

    # Column order in the grid: Name (index 0), City (index 1), Score (index 2)
    # We'll determine actual indices from the table schema
    r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
    if r.status_code != 200:
        fatal(f"get table schema: {r.status_code} {r.text[:200]}")
    columns = r.json().get("columns", [])
    col_order = [c["column_id"] for c in columns]
    idx_name = col_order.index(col_name)
    idx_city = col_order.index(col_city)
    idx_score = col_order.index(col_score)
    print(f"[setup] col indices: Name={idx_name}, City={idx_city}, Score={idx_score}")

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

        # ── Navigate to table ────────────────────────────────────────────────
        wait_table_page(page, ws_name, TABLE_ID)

        try:
            page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=10000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_no_rows")
            fatal("Rows not visible after page load")

        snap(page, "inline_edit_01_initial")
        print("[ok] table loaded with rows visible")

        # ── Test 1: Edit text cell (Alice's City: Tokyo → Osaka) ─────────────
        cell_city_alice = get_cell_locator(page, rid_alice, idx_city)
        cell_city_alice.click()
        page.wait_for_timeout(300)

        # An input should appear inside the cell
        input_loc = cell_city_alice.locator("input")
        try:
            input_loc.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_no_input")
            fatal("Edit input did not appear after clicking text cell")

        snap(page, "inline_edit_02_editing_city")

        # Clear and type new value
        input_loc.fill("Osaka")
        input_loc.press("Enter")
        page.wait_for_timeout(500)

        snap(page, "inline_edit_03_after_commit_city")

        # Verify DB via API
        row_api = get_row_from_api(token, TABLE_ID, rid_alice)
        db_city = row_api["row_data"].get(col_city)
        if db_city != "Osaka":
            fatal(f"DB verification failed: expected City='Osaka', got {db_city!r}")
        print("[ok] text cell edit committed to DB (Tokyo → Osaka)")

        # ── Test 2: Edit number cell (Bob's Score: 200 → 999) ────────────────
        cell_score_bob = get_cell_locator(page, rid_bob, idx_score)
        cell_score_bob.click()
        page.wait_for_timeout(300)

        input_loc = cell_score_bob.locator("input")
        try:
            input_loc.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_no_number_input")
            fatal("Edit input did not appear after clicking number cell")

        snap(page, "inline_edit_04_editing_score")

        input_loc.fill("999")
        input_loc.press("Enter")
        page.wait_for_timeout(500)

        snap(page, "inline_edit_05_after_commit_score")

        row_api = get_row_from_api(token, TABLE_ID, rid_bob)
        db_score = row_api["row_data"].get(col_score)
        if db_score != 999:
            fatal(f"DB verification failed: expected Score=999, got {db_score!r}")
        print("[ok] number cell edit committed to DB (200 → 999)")

        # ── Test 3: Escape cancels edit (Alice's Name: Alice, try → "Zara") ──
        cell_name_alice = get_cell_locator(page, rid_alice, idx_name)
        cell_name_alice.click()
        page.wait_for_timeout(300)

        input_loc = cell_name_alice.locator("input")
        try:
            input_loc.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_no_escape_input")
            fatal("Edit input did not appear for escape test")

        input_loc.fill("Zara")
        input_loc.press("Escape")
        page.wait_for_timeout(500)

        snap(page, "inline_edit_06_after_escape")

        row_api = get_row_from_api(token, TABLE_ID, rid_alice)
        db_name = row_api["row_data"].get(col_name)
        if db_name != "Alice":
            fatal(f"Escape did not cancel: expected Name='Alice', got {db_name!r}")
        print("[ok] Escape cancels edit — no DB change (Name still 'Alice')")

        # ── Test 4: Blur commits edit (Bob's City: Berlin → Munich) ──────────
        cell_city_bob = get_cell_locator(page, rid_bob, idx_city)
        cell_city_bob.click()
        page.wait_for_timeout(300)

        input_loc = cell_city_bob.locator("input")
        try:
            input_loc.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_no_blur_input")
            fatal("Edit input did not appear for blur test")

        input_loc.fill("Munich")
        # Click on a different cell to trigger blur
        cell_name_alice = get_cell_locator(page, rid_alice, idx_name)
        cell_name_alice.click()
        page.wait_for_timeout(500)

        snap(page, "inline_edit_07_after_blur")

        row_api = get_row_from_api(token, TABLE_ID, rid_bob)
        db_city = row_api["row_data"].get(col_city)
        if db_city != "Munich":
            fatal(f"Blur commit failed: expected City='Munich', got {db_city!r}")
        print("[ok] blur commits edit to DB (Berlin → Munich)")

        # ── Test 5: Reload page → edits persisted ────────────────────────────
        wait_table_page(page, ws_name, TABLE_ID)

        try:
            page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=10000)
        except PlaywrightTimeout:
            snap(page, "inline_edit_FAIL_reload")
            fatal("Rows not visible after reload")

        snap(page, "inline_edit_08_after_reload")

        # Verify displayed values after reload
        cell_city_alice = get_cell_locator(page, rid_alice, idx_city)
        city_text = cell_city_alice.inner_text()
        if "Osaka" not in city_text:
            fatal(f"After reload: Alice's City not showing 'Osaka', got {city_text!r}")

        cell_score_bob = get_cell_locator(page, rid_bob, idx_score)
        score_text = cell_score_bob.inner_text()
        if "999" not in score_text:
            fatal(f"After reload: Bob's Score not showing '999', got {score_text!r}")

        print("[ok] edits persist after page reload")

        browser.close()

    # ── Teardown ──────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_view_table_inline_edit ===")


if __name__ == "__main__":
    main()
