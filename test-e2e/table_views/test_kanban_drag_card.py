"""E2E test: Kanban drag card — drag a card between columns updates the row.

Scenario:
  1. Create workspace + PM table (auto-creates Sprint Board kanban view).
  2. Create a row in the "todo" lane.
  3. Navigate to the Sprint Board kanban view.
  4. Verify the card appears in the "todo" lane.
  5. Drag the card to the "in_progress" lane.
  6. Wait for PUT /rows/{row_id} to fire and resolve.
  7. API verify: row's Status field = "in_progress".
  8. UI verify: card appears in "in_progress" lane; absent from "todo" lane.
  9. Navigate away and back.
  10. API verify: row still has Status = "in_progress" (persisted in DB).
  11. UI verify: card is in "in_progress" lane after re-navigation.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e pytest table_views/test_kanban_drag_card.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


SOURCE_LANE = "todo"
DEST_LANE = "in_progress"


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


def test_kanban_drag_card(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table

    # Find kanban view (Sprint Board)
    kanban_views = [v for v in views if v.get("type") == "kanban"]
    assert kanban_views, (
        f"PM template has no kanban view; types={[v.get('type') for v in views]}"
    )
    kanban_view = kanban_views[0]
    kanban_view_id = kanban_view["view_id"]
    group_by_col_id = kanban_view.get("config", {}).get("group_by")
    assert group_by_col_id, "Kanban view has no group_by configured"
    print(f"[ok] kanban view_id={kanban_view_id}  group_by={group_by_col_id!r}")

    # Verify source and destination lane values exist as choices
    status_col = next((c for c in columns if c["column_id"] == group_by_col_id), None)
    assert status_col, f"Could not find group_by column {group_by_col_id!r} in schema"
    choices = [ch["value"] for ch in status_col.get("options", {}).get("choices", [])]
    assert SOURCE_LANE in choices and DEST_LANE in choices, (
        f"Expected choices {SOURCE_LANE!r},{DEST_LANE!r} in {choices}"
    )
    print(f"[ok] status choices include {SOURCE_LANE!r} and {DEST_LANE!r}")

    # Create a row in the source lane
    r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
            json={"row_data": {group_by_col_id: SOURCE_LANE}})
    assert r.status_code == 201, f"create row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] created row {row_id} in {SOURCE_LANE!r} lane")

    # ── Playwright session ────────────────────────────────────────────────
    goto_table(page, ws_id, table_id)

    # ── Step 1: Navigate to Sprint Board tab ──────────────────────────
    try:
        sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
        sprint_tab.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_tab", snapshot)
        pytest.fail("Sprint Board tab not visible")
    sprint_tab.click()
    print("[ok] clicked Sprint Board tab")

    # Wait for kanban to render (card-fields button is the sentinel)
    try:
        cf_btn = page.locator('[data-testid="kanban-card-fields-btn"]')
        cf_btn.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_kanban", snapshot)
        pytest.fail("Kanban card-fields button not visible — board did not render")

    snap(page, "kb_drag_01_kanban_loaded", snapshot)
    print("[ok] kanban view loaded")

    # ── Step 2: Verify card is in source lane ─────────────────────────
    source_lane = page.locator(f'[data-testid="kanban-lane-{SOURCE_LANE}"]')
    try:
        source_lane.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_source_lane", snapshot)
        pytest.fail(f"Source lane (data-testid=kanban-lane-{SOURCE_LANE}) not visible")

    card_sel = f'[data-testid="kanban-card-{row_id}-btn"]'
    card_in_source = source_lane.locator(card_sel)
    try:
        card_in_source.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_card_not_in_source", snapshot)
        pytest.fail(f"Card {row_id} not visible in {SOURCE_LANE!r} lane before drag")

    snap(page, "kb_drag_02_card_in_source", snapshot)
    print(f"[ok] card {row_id} visible in {SOURCE_LANE!r} lane")

    # ── Step 3: Drag card to destination lane ─────────────────────────
    dest_lane = page.locator(f'[data-testid="kanban-lane-{DEST_LANE}"]')
    try:
        dest_lane.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_dest_lane", snapshot)
        pytest.fail(f"Destination lane (data-testid=kanban-lane-{DEST_LANE}) not visible")

    card_el = page.locator(card_sel)
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/rows/{row_id}" in resp.url
            and resp.request.method == "PUT"
        ),
        timeout=15000,
    ):
        card_el.drag_to(dest_lane)

    print(f"[ok] dragged card {row_id} to {DEST_LANE!r} — PUT fired")

    # ── Step 4: API verify — row's status updated ─────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
    assert r.status_code == 200, f"GET row: {r.status_code} {r.text[:200]}"
    row_data = r.json().get("row_data", {})
    actual_val = row_data.get(group_by_col_id)
    assert actual_val == DEST_LANE, (
        f"API: row {row_id} has {group_by_col_id!r}={actual_val!r}, "
        f"expected {DEST_LANE!r}"
    )
    print(f"[ok] API: row {row_id} status={DEST_LANE!r}")

    # ── Step 5: UI verify — card in dest lane, absent from source ─────
    card_in_dest = dest_lane.locator(card_sel)
    try:
        card_in_dest.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_card_not_in_dest", snapshot)
        pytest.fail(f"Card {row_id} not visible in {DEST_LANE!r} lane after drag")

    card_in_source_after = source_lane.locator(card_sel)
    try:
        card_in_source_after.wait_for(state="hidden", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_card_still_in_source", snapshot)
        pytest.fail(f"Card {row_id} still visible in {SOURCE_LANE!r} lane after drag")

    snap(page, "kb_drag_03_card_in_dest", snapshot)
    print(f"[ok] UI: card {row_id} in {DEST_LANE!r}, absent from {SOURCE_LANE!r}")

    # ── Step 6: Navigate away and back → verify persistence ───────────
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id)

    try:
        sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
        sprint_tab2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_tab_after_nav", snapshot)
        pytest.fail("Sprint Board tab not visible after navigation back")
    sprint_tab2.click()

    try:
        cf_btn2 = page.locator('[data-testid="kanban-card-fields-btn"]')
        cf_btn2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_kanban_after_nav", snapshot)
        pytest.fail("Kanban board not visible after navigation back")

    # API verify persistence
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
    assert r.status_code == 200, f"GET row after nav: {r.status_code} {r.text[:200]}"
    row_data_after = r.json().get("row_data", {})
    actual_val_after = row_data_after.get(group_by_col_id)
    assert actual_val_after == DEST_LANE, (
        f"Persistence: row {row_id} has {group_by_col_id!r}={actual_val_after!r}, "
        f"expected {DEST_LANE!r}"
    )
    print(f"[ok] API: row {row_id} status persisted as {DEST_LANE!r} after navigation")

    # UI verify persistence
    dest_lane2 = page.locator(f'[data-testid="kanban-lane-{DEST_LANE}"]')
    try:
        dest_lane2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_no_dest_after_nav", snapshot)
        pytest.fail(f"Dest lane {DEST_LANE!r} not visible after navigation back")

    card_in_dest2 = dest_lane2.locator(card_sel)
    try:
        card_in_dest2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_drag_FAIL_card_not_persisted", snapshot)
        pytest.fail(
            f"Card {row_id} not visible in {DEST_LANE!r} lane after navigation back"
        )

    snap(page, "kb_drag_04_persisted", snapshot)
    print(f"[ok] UI: card {row_id} persists in {DEST_LANE!r} lane after navigation")

    print("\n=== PASSED — test_kanban_drag_card ===")
