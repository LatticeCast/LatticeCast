#!/usr/bin/env python3
"""E2E test: column_delete — delete propagates to all views.

Topic: Deleting a column via the Table-view header menu removes it from:
  - DB schema (columns array)
  - Table view (col-header detached)
  - Kanban view (group-by option + card-field checkbox gone)
  - Timeline view (group-by option gone)
The deletion is durable across navigation.

Three pillars (developing-e2e):
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
  teardown: DELETE workspace (via conftest workspace fixture)

Usage:
    docker compose exec e2e pytest tables/test_column_delete.py -v
    docker compose exec e2e pytest tables/test_column_delete.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        try:
            page.screenshot(path=f"/output/{name}.png", full_page=True)
        except Exception:
            pass


def goto_table(page, ws_id: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "col_del_FAIL_no_view_tabs", snapshot)
        pytest.fail(f"View tabs did not load for table {table_id}")


def option_exists(page, select_testid: str, value: str) -> bool:
    """Check if a <select> with given testid contains an <option> with given value."""
    return page.locator(
        f'[data-testid="{select_testid}"] option[value="{value}"]'
    ).count() > 0


def test_column_delete_propagates(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace

    _suffix = int(time.time()) % 100000
    table_id = f"col-del-{_suffix}"

    print(f"[ok] login 'lattice'")

    # ── setup: PM table + Table view + custom select column ───────────────
    r = api("POST", "/api/v1/tables/template/pm", token,
            json={"table_id": table_id, "workspace_name": ws_name})
    assert r.status_code == 201, f"create PM table: {r.status_code} {r.text[:200]}"
    print(f"[ok] PM table {table_id!r}")

    r = api("POST", f"/api/v1/tables/{table_id}/views", token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code == 201, f"add Table view: {r.status_code} {r.text[:200]}"
    print("[ok] added 'Table' view")

    r = api("POST", f"/api/v1/tables/{table_id}/columns", token,
            json={"name": "TestCol", "type": "select",
                  "options": [{"label": "Alpha"}, {"label": "Beta"}]})
    assert r.status_code == 201, f"create TestCol column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    test_col = next((c for c in schema["columns"] if c.get("name") == "TestCol"), None)
    assert test_col, f"TestCol missing from schema; cols={[c['name'] for c in schema['columns']]}"
    col_id = test_col["column_id"]
    print(f"[ok] TestCol (select) created → {col_id[:8]}…")

    # API pre-check
    r_pre = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r_pre.status_code == 200, f"GET table pre-check: {r_pre.status_code}"
    pre_ids = [c["column_id"] for c in r_pre.json()["columns"]]
    assert col_id in pre_ids, f"TestCol {col_id[:8]}… absent from schema before test starts"

    # ── browser session ───────────────────────────────────────────────────
    goto_table(page, ws_id, table_id, snapshot)

    # Switch to Table view
    table_tab = '[data-testid="view-tab-Table"]'
    page.wait_for_selector(table_tab, state="visible", timeout=8000)
    page.click(table_tab)

    col_header_sel = f'[data-testid="col-header-{col_id}"]'
    page.wait_for_selector(col_header_sel, state="visible", timeout=15000)
    snap(page, "col_del_01_before_delete", snapshot)
    print("[ok] UI pre-check: TestCol col-header visible in Table view")

    # ── step 1: open col menu → Delete ────────────────────────────────────
    col_toggle_sel = f'[data-testid="col-menu-toggle-{col_id}"]'
    page.wait_for_selector(col_toggle_sel, state="visible", timeout=8000)
    page.click(col_toggle_sel)

    delete_btn_sel = f'[data-testid="col-delete-{col_id}"]'
    page.wait_for_selector(delete_btn_sel, state="visible", timeout=5000)

    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/columns/{col_id}" in resp.url
            and resp.request.method == "DELETE"
            and resp.ok
        ),
        timeout=10000,
    ):
        page.click(delete_btn_sel)
    print("[ok] Delete clicked; DELETE response confirmed")
    snap(page, "col_del_02_after_delete", snapshot)

    # ── step 2: API verify ────────────────────────────────────────────────
    r_post = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r_post.status_code == 200, f"GET table after delete: {r_post.status_code}"
    post_ids = [c["column_id"] for c in r_post.json()["columns"]]
    assert col_id not in post_ids, f"API: TestCol {col_id[:8]}… still in schema after delete!"
    print("[ok] API: TestCol absent from schema")

    # ── step 3: Table view — col-header detached ──────────────────────────
    page.wait_for_selector(col_header_sel, state="detached", timeout=8000)
    print("[ok] Table view: col-header detached")
    snap(page, "col_del_03_table_gone", snapshot)

    # ── step 4: Kanban view — group-by + card-field gone ──────────────────
    kanban_tab = '[data-testid="view-tab-Sprint Board"]'
    page.wait_for_selector(kanban_tab, state="visible", timeout=8000)
    page.click(kanban_tab)

    # Wait for kanban to render (group-by-selector is always visible)
    page.wait_for_selector('[data-testid="group-by-selector"]', state="visible", timeout=10000)

    assert not option_exists(page, "group-by-selector", col_id), \
        f"Kanban: TestCol still in group-by-selector options after delete!"
    print("[ok] Kanban: TestCol absent from group-by-selector")

    # Open card-fields panel and verify checkbox gone
    page.click('[data-testid="kanban-card-fields-btn"]')
    card_field_sel = f'[data-testid="kanban-card-field-{col_id}-checkbox"]'
    assert page.locator(card_field_sel).count() == 0, \
        f"Kanban: TestCol card-field checkbox still present after delete!"
    print("[ok] Kanban: TestCol absent from card-field checkboxes")
    snap(page, "col_del_04_kanban_gone", snapshot)

    # ── step 5: Timeline view — group-by option gone ──────────────────────
    timeline_tab = '[data-testid="view-tab-Roadmap"]'
    page.wait_for_selector(timeline_tab, state="visible", timeout=8000)
    page.click(timeline_tab)

    page.wait_for_selector(
        '[data-testid="timeline-group-by-select"]', state="visible", timeout=10000
    )

    assert not option_exists(page, "timeline-group-by-select", col_id), \
        f"Timeline: TestCol still in group-by-select options after delete!"
    print("[ok] Timeline: TestCol absent from timeline-group-by-select")
    snap(page, "col_del_05_timeline_gone", snapshot)

    # ── step 6: durability — navigate away and back ───────────────────────
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id, snapshot)

    # Table view durability
    page.wait_for_selector(table_tab, state="visible", timeout=8000)
    page.click(table_tab)
    page.wait_for_selector("table thead", state="visible", timeout=15000)

    r_dur = api("GET", f"/api/v1/tables/{table_id}", token)
    dur_ids = [c["column_id"] for c in r_dur.json()["columns"]]
    assert col_id not in dur_ids, f"Durability API: TestCol reappeared!"
    assert page.query_selector(col_header_sel) is None, \
        f"Durability Table UI: col-header reappeared!"
    print("[ok] Durability: Table view correct after nav")

    # Kanban durability
    page.click(kanban_tab)
    page.wait_for_selector('[data-testid="group-by-selector"]', state="visible", timeout=10000)
    assert not option_exists(page, "group-by-selector", col_id), \
        f"Durability Kanban: TestCol reappeared in group-by-selector!"
    print("[ok] Durability: Kanban view correct after nav")

    # Timeline durability
    page.click(timeline_tab)
    page.wait_for_selector(
        '[data-testid="timeline-group-by-select"]', state="visible", timeout=10000
    )
    assert not option_exists(page, "timeline-group-by-select", col_id), \
        f"Durability Timeline: TestCol reappeared in group-by-select!"
    print("[ok] Durability: Timeline view correct after nav")

    snap(page, "col_del_06_durability_done", snapshot)

    print("\n=== PASSED — test_column_delete ===")
