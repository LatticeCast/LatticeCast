"""E2E test: datetime column type, end to end.

Topic: A `datetime` column is creatable through the API, and both
`datetime` and `date` cells store the one canonical shape — a JSON number
of epoch milliseconds, UTC+0 — with `date` landing on UTC midnight, an
unparseable value refused as a client error, and an empty cell reading
back `null` rather than `0`.

Three pillars (developing-e2e):
  - BE API verify — schema snapshot carries type "datetime"; cells read
                    back as epoch-millisecond integers
  - DB semantics  — UTC-midnight alignment for `date`, null-vs-zero for
                    an emptied cell, 4xx for unparseable input
  - Playwright UI — the datetime column header and its cell render in the
                    grid; snapshot saved for inspection

Flow:
  setup:  login as "lattice" -> create workspace -> create blank table
          -> add a datetime column and a date column -> create a table
          view -> create one row
  step 1: API — schema snapshot contains the datetime column, type intact
  step 2: API — write "2026-05-01T12:30:45Z", read back 1746102645000
  step 3: API — write "2026-05-01" to the date column, read back
                1746057600000, UTC-midnight aligned
  step 4: API — write "not a date", assert 4xx (not a 500 index cast)
  step 5: API — clear the datetime cell, read back null (never 0)
  step 6: API — restore the value for the rendered check
  step 7: UI  — the datetime column header and row cell render; snapshot
  teardown: DELETE workspace (workspace fixture)

Usage:
    docker compose exec -T e2e pytest tables/test_column_datetime_type.py -v
    docker compose exec -T e2e pytest tables/test_column_datetime_type.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

DT_COL = "Event At"
DATE_COL = "Event Day"

# Spelled out rather than computed so the test states the contract
# instead of re-deriving it with the same arithmetic it is meant to
# check.
#
# task-61 quoted 1746102645000 / 1746057600000 for these two inputs.
# Those are the epoch milliseconds of 2025-05-01, not 2026-05-01 -- the
# ticket's constants are a year behind its own ISO strings. The inputs
# below are the ones the ticket specified; the expectations are the
# values they actually denote.
DT_ISO = "2026-05-01T12:30:45Z"
DT_MS = 1777638645000

DATE_ISO = "2026-05-01"
DATE_MS = 1777593600000

DAY_MS = 86400000


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        page.screenshot(path=f"/output/{name}.png", full_page=True)


def read_cell(token: str, table_id: str, row_id: int, col_id: str):
    """GET the row and return one cell exactly as the API reports it."""
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
    assert r.status_code == 200, f"GET row: {r.status_code} {r.text[:200]}"
    return r.json()["row_data"].get(col_id)


def patch_cell(token: str, table_id: str, row_id: int, col_id: str, value):
    return api(
        "PATCH", f"/api/v1/tables/{table_id}/rows/{row_id}", token,
        json={"row_data": {col_id: value}},
    )


def add_column(token: str, table_id: str, name: str, col_type: str) -> str:
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token,
            json={"name": name, "type": col_type})
    assert r.status_code == 201, f"add {col_type} column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    col = next((c for c in schema["columns"] if c["name"] == name), None)
    assert col is not None, (
        f"column {name!r} missing from returned schema snapshot; "
        f"got {[c['name'] for c in schema['columns']]}"
    )
    assert col["type"] == col_type, f"column {name!r} type={col['type']!r}, expected {col_type!r}"
    return col["column_id"]


def goto_table(page, ws_name: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-table-loaded="true"]', state="attached", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "dt_FAIL_table_not_loaded", snapshot)
        pytest.fail(f"Table {table_id!r} did not finish loading")


def test_datetime_column_type(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace

    table_id = f"dt-{int(time.time() * 1000) % 10_000_000}"

    # ── setup: blank table, both temporal columns, a view, one row ─────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[ok] table {table_id!r}")

    # ── step 1: API — datetime is accepted by the column contract ──────────
    dt_col = add_column(token, table_id, DT_COL, "datetime")
    print(f"[ok] API: datetime column {DT_COL!r} -> {dt_col[:8]}…")

    date_col = add_column(token, table_id, DATE_COL, "date")
    print(f"[ok] API: date column {DATE_COL!r} -> {date_col[:8]}…")

    # The type must survive a fresh read of the schema, not just the
    # mutation response that created it.
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r.status_code == 200, f"GET table: {r.status_code} {r.text[:200]}"
    persisted = next((c for c in r.json()["columns"] if c["column_id"] == dt_col), None)
    assert persisted is not None, "datetime column absent from re-read schema"
    assert persisted["type"] == "datetime", f"re-read type={persisted['type']!r}, expected 'datetime'"
    print("[ok] API: type 'datetime' persisted in the schema")

    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code in (200, 201), f"create table view: {r.status_code} {r.text[:200]}"

    r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": {}})
    assert r.status_code in (200, 201), f"create row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] row id={row_id}")

    # ── step 2: API — ISO datetime normalises to epoch milliseconds ────────
    r = patch_cell(token, table_id, row_id, dt_col, DT_ISO)
    assert r.status_code == 200, f"PATCH datetime: {r.status_code} {r.text[:200]}"
    stored = read_cell(token, table_id, row_id, dt_col)
    assert stored == DT_MS, f"datetime cell={stored!r}, expected {DT_MS}"
    assert isinstance(stored, int) and not isinstance(stored, bool), (
        f"datetime cell must be a JSON number, got {type(stored).__name__}"
    )
    print(f"[ok] API: {DT_ISO} -> {stored}")

    # ── step 3: API — a date cell lands on UTC midnight ────────────────────
    r = patch_cell(token, table_id, row_id, date_col, DATE_ISO)
    assert r.status_code == 200, f"PATCH date: {r.status_code} {r.text[:200]}"
    stored = read_cell(token, table_id, row_id, date_col)
    assert stored == DATE_MS, f"date cell={stored!r}, expected {DATE_MS}"
    assert stored % DAY_MS == 0, f"date cell {stored} is not UTC-midnight aligned"
    print(f"[ok] API: {DATE_ISO} -> {stored} (midnight aligned)")

    # ── step 4: API — unparseable input is a client error ──────────────────
    r = patch_cell(token, table_id, row_id, dt_col, "not a date")
    assert 400 <= r.status_code < 500, (
        f"unparseable datetime returned {r.status_code}, expected 4xx "
        f"(a 5xx means the bad value escaped validation): {r.text[:300]}"
    )
    print(f"[ok] API: 'not a date' rejected with {r.status_code}")

    # The refused write must not have disturbed the stored value.
    stored = read_cell(token, table_id, row_id, dt_col)
    assert stored == DT_MS, f"after rejected write datetime cell={stored!r}, expected {DT_MS}"
    print("[ok] API: rejected write left the cell unchanged")

    # ── step 5: API — an emptied cell is null, never 0 ─────────────────────
    r = patch_cell(token, table_id, row_id, dt_col, None)
    assert r.status_code == 200, f"PATCH clear: {r.status_code} {r.text[:200]}"
    stored = read_cell(token, table_id, row_id, dt_col)
    assert stored is None, f"cleared datetime cell={stored!r}, expected None (0 would be 1970-01-01T00:00:00Z)"
    print("[ok] API: cleared cell reads back null, not 0")

    # ── step 6: restore the value so the grid has something to render ──────
    r = patch_cell(token, table_id, row_id, dt_col, DT_ISO)
    assert r.status_code == 200, f"PATCH restore: {r.status_code} {r.text[:200]}"
    assert read_cell(token, table_id, row_id, dt_col) == DT_MS

    # ── step 7: UI — the datetime column renders in the grid ───────────────
    goto_table(page, ws_name, table_id, snapshot)

    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "dt_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    header = f'[data-testid="col-header-{dt_col}"]'
    try:
        page.wait_for_selector(header, state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "dt_FAIL_no_header", snapshot)
        pytest.fail(f"datetime column header {DT_COL!r} not rendered in the grid")
    assert DT_COL in page.inner_text(header), (
        f"datetime column header text={page.inner_text(header)!r}, expected to contain {DT_COL!r}"
    )
    print(f"[ok] UI: column header {DT_COL!r} rendered")

    # The datetime cell itself must render the stored value. The frontend
    # has no datetime renderer yet (story-54 keeps that in the frontend
    # epic), so it falls through to the raw epoch-millisecond number --
    # assert the cell carries the value rather than a specific format.
    row_sel = f'[data-testid="grid-row-{row_id}"]'
    page.wait_for_selector(row_sel, state="visible", timeout=10000)
    page.wait_for_function(
        f'document.querySelector({row_sel!r})?.innerText.includes("{DT_MS}")',
        timeout=5000,
    )
    print(f"[ok] UI: datetime cell renders the stored value {DT_MS}")

    snap(page, "dt_01_datetime_column", snapshot)

    print("\n=== PASSED — test_column_datetime_type ===")
