#!/usr/bin/env python3
"""E2E test: + Add row appears in all views.

Scenario:
  1. Create workspace + PM table (auto-creates Table, Sprint Board, Roadmap views).
  2. Navigate to Table view, click '+ Add row'.
  3. API verify: new row exists in backend.
  4. Update row with title, status, dates (needed for kanban lane + timeline bar).
  5. Reload page — verify row in Table view.
  6. Switch to Kanban (Sprint Board) — verify card.
  7. Switch to Timeline (Roadmap) — verify bar.
  8. Navigate away and back — verify persistence in all three views.

Run:
    docker compose --profile test up -d browser e2e
    docker compose exec -T e2e pytest tables/test_row_create.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


_TS = int(time.time()) % 100000

ROW_TITLE = f"test-row-{_TS}"
ROW_STATUS = "todo"
ROW_START_DATE = "2026-06-01"
ROW_END_DATE = "2026-06-15"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="networkidle")
    try:
        page.wait_for_selector(
            '[data-table-loaded="true"]', state="attached", timeout=15000
        )
    except PlaywrightTimeout:
        pytest.fail(f"Table page did not load for {table_id}")


def switch_to_table_view(page) -> None:
    """Click the Schema (table) tab and wait for the grid to render."""
    page.locator('[data-testid="view-tab-Schema"]').click()
    page.locator('[data-testid="grid-add-row-btn"]').wait_for(
        state="visible", timeout=10000
    )


def test_row_create_appears_in_all_views(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table
    print(f"[ok] PM table {table_id!r} (cols={len(columns)}, views={len(views)})")

    # Identify key columns
    title_col = next(
        (c for c in columns if c.get("name") == "Title" and c["type"] in ("text", "string")),
        next((c for c in columns if c["type"] in ("text", "string")), None),
    )
    status_col = next(
        (c for c in columns if c.get("name") == "Status" and c["type"] == "select"), None
    )
    assert title_col, f"No text column found: {[c['name'] for c in columns]}"
    assert status_col, f"No Status column found: {[c['name'] for c in columns]}"

    # Get view configs
    timeline_views = [v for v in views if v.get("type") == "timeline"]
    kanban_views = [v for v in views if v.get("type") == "kanban"]
    assert timeline_views, f"No timeline view; types={[v.get('type') for v in views]}"
    assert kanban_views, f"No kanban view; types={[v.get('type') for v in views]}"

    timeline_view = timeline_views[0]
    kanban_view = kanban_views[0]
    start_col_id = timeline_view.get("config", {}).get("start_col")
    end_col_id = timeline_view.get("config", {}).get("end_col")
    kanban_tab_name = kanban_view.get("name", "Sprint Board")
    timeline_tab_name = timeline_view.get("name", "Roadmap")

    assert start_col_id, "Timeline view has no start_col configured"
    print(f"[ok] timeline: start_col={start_col_id!r}, end_col={end_col_id!r}")

    # ── Step 1: Click '+ Add row' in Table view ──────────────────────
    goto_table(page, ws_id, table_id)
    try:
        page.locator('[data-testid="view-tab-Schema"]').wait_for(
            state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        pytest.fail("View tabs did not load")

    switch_to_table_view(page)
    snap(page, "row_create_01_table_view", snapshot)

    new_row_id = None
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/rows" in resp.url
            and resp.request.method == "POST"
        ),
        timeout=15000,
    ) as resp_info:
        page.locator('[data-testid="grid-add-row-btn"]').click()

    post_resp = resp_info.value
    assert post_resp.status == 201, f"POST /rows returned {post_resp.status}"
    new_row_id = post_resp.json().get("row_id")
    assert new_row_id, f"POST /rows response missing row_id: {post_resp.json()}"
    print(f"[ok] POST /rows → row_id={new_row_id}")

    # ── Step 2: API verify — row exists ──────────────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{new_row_id}", admin_token)
    assert r.status_code == 200, f"GET row {new_row_id}: {r.status_code} {r.text[:200]}"
    print(f"[ok] API: row {new_row_id} exists")

    # ── Step 3: Update row with title, status, dates ─────────────────
    row_data = {
        title_col["column_id"]: ROW_TITLE,
        status_col["column_id"]: ROW_STATUS,
        start_col_id: ROW_START_DATE,
    }
    if end_col_id:
        row_data[end_col_id] = ROW_END_DATE
    r = api(
        "PUT", f"/api/v1/tables/{table_id}/rows/{new_row_id}", admin_token,
        json={"row_data": row_data},
    )
    assert r.status_code == 200, f"PUT row {new_row_id}: {r.status_code} {r.text[:200]}"
    print(f"[ok] API: updated row with title/status/dates")

    # ── Step 4: Reload and verify in Table view ──────────────────────
    goto_table(page, ws_id, table_id)
    switch_to_table_view(page)

    row_sel = f'[data-testid="grid-row-{new_row_id}"]'
    try:
        page.locator(row_sel).wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_no_row_in_grid", snapshot)
        pytest.fail(f"Row {new_row_id} not visible in table grid")

    snap(page, "row_create_02_row_in_table", snapshot)
    print(f"[ok] UI: row {new_row_id} visible in table grid")

    # ── Step 5: Switch to Kanban — verify card ───────────────────────
    kanban_tab = page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]')
    try:
        kanban_tab.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        pytest.fail(f"Kanban tab '{kanban_tab_name}' not visible")
    kanban_tab.click()

    try:
        page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
            state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_kanban_not_loaded", snapshot)
        pytest.fail("Kanban board did not load")

    card_sel = f'[data-testid="kanban-card-{new_row_id}-btn"]'
    try:
        page.locator(card_sel).wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_card_not_in_kanban", snapshot)
        pytest.fail(f"Card {new_row_id} not visible in kanban view")

    snap(page, "row_create_03_card_in_kanban", snapshot)
    print(f"[ok] UI: card {new_row_id} visible in kanban ({kanban_tab_name})")

    # ── Step 6: Switch to Timeline — verify bar ──────────────────────
    timeline_tab = page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]')
    try:
        timeline_tab.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        pytest.fail(f"Timeline tab '{timeline_tab_name}' not visible")
    timeline_tab.click()

    bar_sel = f'[data-testid="timeline-row-bar-{new_row_id}"]'
    try:
        page.locator(bar_sel).wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_bar_not_in_timeline", snapshot)
        pytest.fail(f"Bar {new_row_id} not visible in timeline view")

    snap(page, "row_create_04_bar_in_timeline", snapshot)
    print(f"[ok] UI: bar {new_row_id} visible in timeline ({timeline_tab_name})")

    # ── Step 7: Navigate away and back — verify persistence ──────────
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id)

    # API verify persistence
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{new_row_id}", admin_token)
    assert r.status_code == 200, f"GET row after nav: {r.status_code} {r.text[:200]}"
    persisted = r.json().get("row_data", {})
    assert persisted.get(title_col["column_id"]) == ROW_TITLE, \
        f"Title not persisted: {persisted.get(title_col['column_id'])!r}"
    assert persisted.get(status_col["column_id"]) == ROW_STATUS, \
        f"Status not persisted: {persisted.get(status_col['column_id'])!r}"
    print(f"[ok] API: row {new_row_id} data persists after navigation")

    # Table view persistence
    switch_to_table_view(page)
    try:
        page.locator(row_sel).wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_row_gone_table", snapshot)
        pytest.fail(f"Row {new_row_id} not in table after navigation")
    print(f"[ok] UI: row {new_row_id} persists in table after navigation")

    # Kanban persistence
    page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]').click()
    try:
        page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
            state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        pytest.fail("Kanban board did not load after navigation")
    try:
        page.locator(card_sel).wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_card_gone_kanban", snapshot)
        pytest.fail(f"Card {new_row_id} not in kanban after navigation")
    print(f"[ok] UI: card {new_row_id} persists in kanban after navigation")

    # Timeline persistence
    page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]').click()
    try:
        page.locator(bar_sel).wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "row_create_FAIL_bar_gone_timeline", snapshot)
        pytest.fail(f"Bar {new_row_id} not in timeline after navigation")
    print(f"[ok] UI: bar {new_row_id} persists in timeline after navigation")

    snap(page, "row_create_05_all_persisted", snapshot)

    print("\n=== PASSED — test_row_create ===")
