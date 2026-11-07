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
    docker compose --profile test up -d browser e2e
    docker compose exec -T e2e pytest tables/test_inline_edit.py -v [--snapshot]
"""

from __future__ import annotations

from urllib.parse import urlparse

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

_TS = int(time.time())
TABLE_NAME = f"inline-edit-{_TS}"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def wait_table_page(page, ws_name: str, table_name: str) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_name}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        pytest.fail(f"Table page did not finish loading for {table_id!r}")


def get_row_from_api(token: str, table_id: str, row_id: int) -> dict:
    """Fetch a single row from the API to verify DB state."""
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row {row_id}: {r.status_code} {r.text[:200]}"
    return r.json()


def get_cell_locator(page, row_id: int, col_index: int):
    """Get a locator for the nth data cell (0-based) in a grid row.

    Layout: td[0]=row-number (sticky), td[1..N]=data columns in order.
    So col_index 0 → td:nth-child(2).
    """
    row = page.locator(f'[data-testid="grid-row-{row_id}"]')
    return row.locator(f"td:nth-child({col_index + 2})")


def is_row_patch(response, table_id: str, row_id: int) -> bool:
    return response.request.method == "PATCH" and response.url.endswith(
        f"/api/v1/tables/{table_id}/rows/{row_id}"
    )


def test_inline_edit(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    ws_id, ws_name = workspace
    table_name = TABLE_NAME

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", admin_token, json={"table_name": table_name, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    table_id = str(r.json()["table_id"])
    print(f"[setup] table {table_id!r}")

    # ── Setup: columns (Name text, City text, Score number) ──────────────────
    col_ids = {}
    col_types = {"Name": "text", "City": "text", "Score": "number"}
    for name, ctype in col_types.items():
        r = api("POST", f"/api/v1/tables/{table_id}/columns", admin_token,
                json={"name": name, "type": ctype})
        assert r.status_code in (200, 201), f"create column {name!r}: {r.status_code} {r.text[:200]}"
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        assert col, f"column {name!r} not found in schema"
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
        r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
                json={"row_data": row_data})
        assert r.status_code == 201, f"create row {rd!r}: {r.status_code} {r.text[:200]}"
        row_ids.append(r.json()["row_id"])
    print(f"[setup] rows: {row_ids}")

    rid_alice, rid_bob = row_ids

    # Column order in the grid: Name (index 0), City (index 1), Score (index 2)
    # We'll determine actual indices from the table schema
    r = api("GET", f"/api/v1/tables/{table_id}", admin_token)
    assert r.status_code == 200, f"get table schema: {r.status_code} {r.text[:200]}"
    columns = r.json().get("columns", [])
    col_order = [c["column_id"] for c in columns]
    idx_name = col_order.index(col_name)
    idx_city = col_order.index(col_city)
    idx_score = col_order.index(col_score)
    print(f"[setup] col indices: Name={idx_name}, City={idx_city}, Score={idx_score}")

    # ── Navigate to table ────────────────────────────────────────────────────
    wait_table_page(page, ws_name, table_name)
    named_path = f"/{ws_name}/{table_name}"
    assert urlparse(page.url).path == named_path

    try:
        page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=10000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_no_rows", snapshot)
        pytest.fail("Rows not visible after page load")

    snap(page, "inline_edit_01_initial", snapshot)
    print("[ok] table loaded with rows visible")

    # ── Test 1: Edit text cell (Alice's City: Tokyo → Osaka) ─────────────
    cell_city_alice = get_cell_locator(page, rid_alice, idx_city)
    cell_city_alice.click()

    # An input should appear inside the cell
    input_loc = cell_city_alice.locator("input")
    try:
        input_loc.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_no_input", snapshot)
        pytest.fail("Edit input did not appear after clicking text cell")

    snap(page, "inline_edit_02_editing_city", snapshot)

    # Clear and type new value
    input_loc.fill("Osaka")
    with page.expect_response(lambda response: is_row_patch(response, table_id, rid_alice)) as saved:
        input_loc.press("Enter")
    assert saved.value.status == 200, f"City PATCH failed: {saved.value.status}"
    input_loc.wait_for(state="detached", timeout=10000)

    snap(page, "inline_edit_03_after_commit_city", snapshot)

    # Verify DB via API
    row_api = get_row_from_api(admin_token, table_id, rid_alice)
    db_city = row_api["row_data"].get(col_city)
    assert db_city == "Osaka", f"DB verification failed: expected City='Osaka', got {db_city!r}"
    print("[ok] text cell edit committed to DB (Tokyo → Osaka)")

    # ── Test 2: Edit number cell (Bob's Score: 200 → 999) ────────────────
    cell_score_bob = get_cell_locator(page, rid_bob, idx_score)
    cell_score_bob.click()

    input_loc = cell_score_bob.locator("input")
    try:
        input_loc.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_no_number_input", snapshot)
        pytest.fail("Edit input did not appear after clicking number cell")

    snap(page, "inline_edit_04_editing_score", snapshot)

    input_loc.fill("999")
    with page.expect_response(lambda response: is_row_patch(response, table_id, rid_bob)) as saved:
        input_loc.press("Enter")
    assert saved.value.status == 200, f"Score PATCH failed: {saved.value.status}"
    input_loc.wait_for(state="detached", timeout=10000)

    snap(page, "inline_edit_05_after_commit_score", snapshot)

    row_api = get_row_from_api(admin_token, table_id, rid_bob)
    db_score = row_api["row_data"].get(col_score)
    assert db_score == 999, f"DB verification failed: expected Score=999, got {db_score!r}"
    print("[ok] number cell edit committed to DB (200 → 999)")

    # ── Test 3: Escape cancels edit (Alice's Name: Alice, try → "Zara") ──
    cell_name_alice = get_cell_locator(page, rid_alice, idx_name)
    cell_name_alice.click()

    input_loc = cell_name_alice.locator("input")
    try:
        input_loc.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_no_escape_input", snapshot)
        pytest.fail("Edit input did not appear for escape test")

    input_loc.fill("Zara")
    input_loc.press("Escape")
    input_loc.wait_for(state="detached", timeout=3000)

    snap(page, "inline_edit_06_after_escape", snapshot)

    row_api = get_row_from_api(admin_token, table_id, rid_alice)
    db_name = row_api["row_data"].get(col_name)
    assert db_name == "Alice", f"Escape did not cancel: expected Name='Alice', got {db_name!r}"
    print("[ok] Escape cancels edit — no DB change (Name still 'Alice')")

    # ── Test 4: Blur commits edit (Bob's City: Berlin → Munich) ──────────
    cell_city_bob = get_cell_locator(page, rid_bob, idx_city)
    cell_city_bob.click()

    input_loc = cell_city_bob.locator("input")
    try:
        input_loc.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_no_blur_input", snapshot)
        pytest.fail("Edit input did not appear for blur test")

    input_loc.fill("Munich")
    # Click on a different cell to trigger blur
    cell_name_alice = get_cell_locator(page, rid_alice, idx_name)
    with page.expect_response(lambda response: is_row_patch(response, table_id, rid_bob)) as saved:
        cell_name_alice.click()
    assert saved.value.status == 200, f"Blur PATCH failed: {saved.value.status}"

    snap(page, "inline_edit_07_after_blur", snapshot)

    row_api = get_row_from_api(admin_token, table_id, rid_bob)
    db_city = row_api["row_data"].get(col_city)
    assert db_city == "Munich", f"Blur commit failed: expected City='Munich', got {db_city!r}"
    print("[ok] blur commits edit to DB (Berlin → Munich)")

    # ── Test 5: Reload the named table page → edits persisted ───────────
    assert urlparse(page.url).path == named_path
    response = page.reload(wait_until="domcontentloaded", timeout=20000)
    assert response and response.ok, f"Reload failed: {response.status if response else None} {page.url}"
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_reload", snapshot)
        pytest.fail(f"Table page did not finish loading after reload: {page.url}")

    try:
        page.wait_for_selector(f'[data-testid="grid-row-{rid_alice}"]', timeout=10000)
    except PlaywrightTimeout:
        snap(page, "inline_edit_FAIL_reload", snapshot)
        pytest.fail("Rows not visible after reload")

    snap(page, "inline_edit_08_after_reload", snapshot)

    # Verify displayed values after reload
    cell_city_alice = get_cell_locator(page, rid_alice, idx_city)
    city_text = cell_city_alice.inner_text()
    assert "Osaka" in city_text, f"After reload: Alice's City not showing 'Osaka', got {city_text!r}"

    cell_score_bob = get_cell_locator(page, rid_bob, idx_score)
    score_text = cell_score_bob.inner_text()
    assert "999" in score_text, f"After reload: Bob's Score not showing '999', got {score_text!r}"

    print("[ok] edits persist after page reload")

    print("\n=== PASSED — test_inline_edit ===")
