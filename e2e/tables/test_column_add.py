"""E2E test: column_add — new column shows everywhere.

Scenario:
  1. Create workspace + blank table with Status (select), Start/End (date)
     columns already in place, plus a Kanban ("Board") and a Timeline ("Gantt")
     view created via API.
  2. Navigate to the table — Schema view is the default for a blank table.
  3. Click '+ Add column', fill in a name (text type), submit.
  4. BE verify: column is present in the POST /columns response schema.
  5. UI verify (Table view): column header appears.
  6. Navigate to Board (Kanban view).
  7. UI verify (Kanban): column appears in the card-fields panel.
  8. Navigate to Gantt (Timeline view).
  9. UI verify (Timeline): column appears in the group_by select options
     (group_by accepts all column types — no type filter).
  10. Navigate away and back to the table.
  11. UI verify (Persistence): column header still visible in Table view.

Three pillars (developing-e2e v0.10.0):
  - Playwright UI    — header, kanban card-field checkbox, timeline group_by option
  - BE API verify    — POST /columns response carries the new column
  - Navigation check — navigate away + back; header persists

Run:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest tables/test_column_add.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


_TS = int(time.time()) % 100000
TABLE_ID = f"coladd-{_TS}"
NEW_COL_NAME = f"E2E Extra Field {_TS}"


def _col_id(schema: dict, name: str) -> str:
    col = next((c for c in schema["columns"] if c["name"] == name), None)
    assert col is not None, (
        f"column {name!r} not found in schema; have: {[c['name'] for c in schema['columns']]}"
    )
    return col["column_id"]


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        pytest.fail(f"View tabs did not load for table {table_id}")


def test_column_add(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    ws_id, _ws_name = workspace
    token = admin_token

    print(f"[ok] login 'lattice'")

    # ── Setup: blank table ────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": ws_id})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[ok] table {TABLE_ID!r}")

    # ── Setup: Status select column (for kanban group_by) ─────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
            json={"name": "Status", "type": "select",
                  "options": {"choices": [
                      {"value": "todo", "color": ""},
                      {"value": "done", "color": ""},
                  ]}})
    assert r.status_code == 201, f"add Status col: {r.status_code} {r.text[:200]}"
    schema = r.json()
    status_col_id = _col_id(schema, "Status")
    print(f"[ok] Status col → {status_col_id}")

    # ── Setup: date columns (for timeline start/end) ───────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
            json={"name": "Start", "type": "date"})
    assert r.status_code == 201, f"add Start col: {r.status_code} {r.text[:200]}"
    schema = r.json()
    start_col_id = _col_id(schema, "Start")
    print(f"[ok] Start col → {start_col_id}")

    r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
            json={"name": "End", "type": "date"})
    assert r.status_code == 201, f"add End col: {r.status_code} {r.text[:200]}"
    schema = r.json()
    end_col_id = _col_id(schema, "End")
    print(f"[ok] End col → {end_col_id}")

    # ── Setup: Kanban view ────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": "Board", "type": "kanban",
                  "config": {"group_by": status_col_id}})
    assert r.status_code == 201, f"create Kanban view: {r.status_code} {r.text[:200]}"
    print("[ok] Kanban view 'Board'")

    # ── Setup: Timeline view ──────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": "Gantt", "type": "timeline",
                  "config": {"start_col": start_col_id, "end_col": end_col_id}})
    assert r.status_code == 201, f"create Timeline view: {r.status_code} {r.text[:200]}"
    print("[ok] Timeline view 'Gantt'")

    # ── Playwright session ────────────────────────────────────────────────
    # Schema view is the default for a blank table (no default_view set).
    goto_table(page, ws_id, TABLE_ID)
    snap(page, "col_add_01_table_loaded", snapshot)
    print("[ok] table loaded (Schema view)")

    # ── Step 1: Open add-column modal ─────────────────────────────────
    # grid-add-column-btn appears in both TableHeader and TableGrid;
    # .first picks the first in DOM order.
    try:
        page.locator('[data-testid="grid-add-column-btn"]').first.wait_for(
            state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_no_add_btn", snapshot)
        pytest.fail("grid-add-column-btn not visible in Schema view")

    page.locator('[data-testid="grid-add-column-btn"]').first.click()

    try:
        page.wait_for_selector(
            '[data-testid="add-column-name-input"]', state="visible", timeout=5000
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_no_modal", snapshot)
        pytest.fail("AddColumnModal did not open after clicking grid-add-column-btn")

    # Default type is 'text' — no interaction with type selector needed.
    page.fill('[data-testid="add-column-name-input"]', NEW_COL_NAME)
    snap(page, "col_add_02_modal_filled", snapshot)
    print(f"[ok] filled column name {NEW_COL_NAME!r} (type=text)")

    # ── Step 2: Submit — capture POST response for BE pillar ──────────
    with page.expect_response(
        lambda resp: f"/api/v1/tables/{TABLE_ID}/columns" in resp.url
        and resp.request.method == "POST"
        and resp.ok,
        timeout=10000,
    ) as resp_info:
        page.click('[data-testid="add-column-submit-btn"]')

    post_schema = resp_info.value.json()
    cols_after = post_schema.get("columns", [])
    new_col = next((c for c in cols_after if c.get("name") == NEW_COL_NAME), None)
    assert new_col is not None, (
        f"[BE] column {NEW_COL_NAME!r} not in POST /columns response; "
        f"columns={[c['name'] for c in cols_after]}"
    )
    new_col_id = new_col["column_id"]
    print(f"[ok] [BE] column present in POST schema (id={new_col_id})")

    # ── Step 3: Table view — column header visible ────────────────────
    try:
        page.wait_for_selector(
            f'[data-testid="col-header-{new_col_id}"]',
            state="visible",
            timeout=5000,
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_no_table_header", snapshot)
        pytest.fail(f"[Table] col-header-{new_col_id} not visible after column add")
    snap(page, "col_add_03_table_header", snapshot)
    print(f"[ok] [Table] col-header-{new_col_id} visible")

    # ── Step 4: Kanban view — column in card-fields panel ─────────────
    try:
        board_tab = page.locator('[data-testid="view-tab-Board"]')
        board_tab.wait_for(state="visible", timeout=10000)
        board_tab.click()
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_no_kanban_tab", snapshot)
        pytest.fail("Kanban tab 'Board' not visible")

    try:
        page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
            state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_kanban_no_render", snapshot)
        pytest.fail("Kanban board did not render (kanban-card-fields-btn not visible)")

    page.click('[data-testid="kanban-card-fields-btn"]')
    try:
        page.wait_for_selector(
            f'[data-testid="kanban-card-field-{new_col_id}-checkbox"]',
            state="visible",
            timeout=5000,
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_kanban_no_field", snapshot)
        pytest.fail(
            f"[Kanban] kanban-card-field-{new_col_id}-checkbox not in card-fields panel"
        )
    snap(page, "col_add_04_kanban_field", snapshot)
    print(f"[ok] [Kanban] card-field-{new_col_id} present in fields panel")

    # ── Step 5: Timeline view — column in group_by select ─────────────
    try:
        gantt_tab = page.locator('[data-testid="view-tab-Gantt"]')
        gantt_tab.wait_for(state="visible", timeout=10000)
        gantt_tab.click()
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_no_timeline_tab", snapshot)
        pytest.fail("Timeline tab 'Gantt' not visible")

    try:
        page.wait_for_selector(
            '[data-testid="timeline-group-by-select"]',
            state="visible",
            timeout=10000,
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_timeline_no_render", snapshot)
        pytest.fail("Timeline view did not render timeline-group-by-select")

    # group_by iterates ALL columns with no type filter — text col must appear.
    option_values = page.locator(
        '[data-testid="timeline-group-by-select"] option'
    ).evaluate_all("opts => opts.map(o => o.value)")
    assert new_col_id in option_values, (
        f"[Timeline] column {new_col_id} not in group_by options: {option_values}"
    )
    snap(page, "col_add_05_timeline_group_by", snapshot)
    print(f"[ok] [Timeline] column {new_col_id} present in group_by select")

    # ── Step 6: Persistence — navigate away and back ──────────────────
    page.goto(f"{BASE}/{ws_id}", wait_until="domcontentloaded")
    # Navigate back; the last-visited view (Gantt) may be restored as
    # default, so explicitly activate Schema to verify the col header.
    goto_table(page, ws_id, TABLE_ID)
    try:
        schema_tab = page.locator('[data-testid="view-tab-Schema"]')
        schema_tab.wait_for(state="visible", timeout=10000)
        schema_tab.click()
        page.wait_for_selector(
            f'[data-testid="col-header-{new_col_id}"]',
            state="visible",
            timeout=5000,
        )
    except PlaywrightTimeout:
        snap(page, "col_add_FAIL_persistence", snapshot)
        pytest.fail(
            f"[Persistence] col-header-{new_col_id} gone after navigate-away + back"
        )
    snap(page, "col_add_06_persistence", snapshot)
    print(f"[ok] [Persistence] col-header-{new_col_id} visible after re-navigation")

    print("PASS  test_column_add")
