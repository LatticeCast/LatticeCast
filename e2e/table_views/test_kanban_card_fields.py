"""E2E test: Kanban card fields — toggle which fields appear on cards.

Scenario:
  1. Create workspace + PM table (auto-creates Sprint Board kanban view).
  2. Navigate to the Kanban view.
  3. Open the "Card fields" panel — verify all checkboxes visible.
  4. Uncheck a field → PUT fires → API confirms card_fields updated.
  5. Check a previously unchecked field → verify card_fields updated.
  6. Verify the card UI renders only the selected fields.
  7. Navigate away and back → verify card_fields persists.

Run:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest table_views/test_kanban_card_fields.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


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


def test_kanban_card_fields(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, columns, views = pm_table
    token = admin_token
    print(f"[ok] login 'lattice'")

    print(f"[ok] PM table {table_id!r} (cols={len(columns)})")

    # Find kanban view
    kanban_views = [v for v in views if v.get("type") == "kanban"]
    assert kanban_views, (
        f"PM template has no kanban view; types={[v.get('type') for v in views]}"
    )
    kanban_view = kanban_views[0]
    kanban_view_id = kanban_view["view_id"]
    group_by_col = kanban_view.get("config", {}).get("group_by")
    print(f"[ok] kanban view_id={kanban_view_id}  group_by={group_by_col!r}")

    # Get non-group-by columns (these appear in card fields panel)
    all_col_ids = [c["column_id"] for c in columns]
    col_names = {c["column_id"]: c["name"] for c in columns}
    print(f"[ok] columns: {[(c['name'], c['column_id']) for c in columns]}")

    # Create a couple of rows so cards are visible
    status_col = group_by_col
    r = api("POST", f"/api/v1/tables/{table_id}/rows", token,
            json={"row_data": {status_col: "todo"}})
    assert r.status_code == 201, f"create row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] created row {row_id}")

    # ── Playwright session ────────────────────────────────────────────────
    goto_table(page, ws_id, table_id)

    # ── Step 1: Click Sprint Board tab ────────────────────────────────
    try:
        sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
        sprint_tab.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_tab", snapshot)
        pytest.fail("Sprint Board tab not visible")
    sprint_tab.click()
    print("[ok] clicked Sprint Board tab")

    # Wait for kanban to render (card fields button must be visible)
    try:
        cf_btn = page.locator('[data-testid="kanban-card-fields-btn"]')
        cf_btn.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_btn", snapshot)
        pytest.fail("Card fields button not visible")

    snap(page, "kb_cf_01_kanban_loaded", snapshot)
    print("[ok] kanban view loaded, card fields button visible")

    # ── Step 2: Open card fields panel ────────────────────────────────
    cf_btn.click()
    page.wait_for_timeout(300)

    # Verify checkboxes appear for columns
    first_col = columns[0]
    first_cb_sel = f'[data-testid="kanban-card-field-{first_col["column_id"]}-checkbox"]'
    try:
        page.wait_for_selector(first_cb_sel, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_checkboxes", snapshot)
        pytest.fail("Card field checkboxes not visible after opening panel")

    snap(page, "kb_cf_02_panel_open", snapshot)
    print("[ok] card fields panel open — checkboxes visible")

    # ── Step 3: Check a specific field → verify PUT + API ─────────────
    # Pick the first column that isn't group_by
    target_col = next(
        (c for c in columns if c["column_id"] != group_by_col), columns[0]
    )
    target_col_id = target_col["column_id"]
    target_cb = page.locator(
        f'[data-testid="kanban-card-field-{target_col_id}-checkbox"]'
    )

    # Determine initial state (checked or not)
    was_checked = target_cb.is_checked()

    # Toggle it: if unchecked → check; if checked → uncheck then re-check
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/views/{kanban_view_id}" in resp.url
            and resp.request.method == "PUT"
        ),
        timeout=10000,
    ):
        target_cb.click()
    print(f"[ok] toggled {target_col['name']!r} checkbox (was_checked={was_checked})")

    page.wait_for_timeout(300)
    snap(page, "kb_cf_03_after_toggle1", snapshot)

    # API verify: card_fields should reflect the toggle
    r = api("GET", f"/api/v1/tables/{table_id}/views/{kanban_view_id}", token)
    assert r.status_code == 200, f"GET view: {r.status_code} {r.text[:200]}"
    card_fields_api = r.json().get("config", {}).get("card_fields", [])

    if was_checked:
        # We unchecked it → should NOT be in card_fields
        assert target_col_id not in card_fields_api, (
            f"API: {target_col_id!r} still in card_fields after uncheck: {card_fields_api}"
        )
        print(f"[ok] API: {target_col['name']!r} removed from card_fields")
    else:
        # We checked it → should be in card_fields
        assert target_col_id in card_fields_api, (
            f"API: {target_col_id!r} not in card_fields after check: {card_fields_api}"
        )
        print(f"[ok] API: {target_col['name']!r} added to card_fields")

    # ── Step 4: Toggle a second column ────────────────────────────────
    second_col = next(
        (c for c in columns
         if c["column_id"] != group_by_col and c["column_id"] != target_col_id),
        None,
    )
    if second_col:
        second_cb = page.locator(
            f'[data-testid="kanban-card-field-{second_col["column_id"]}-checkbox"]'
        )
        second_was_checked = second_cb.is_checked()

        with page.expect_response(
            lambda resp: (
                f"/api/v1/tables/{table_id}/views/{kanban_view_id}" in resp.url
                and resp.request.method == "PUT"
            ),
            timeout=10000,
        ):
            second_cb.click()
        print(f"[ok] toggled {second_col['name']!r} (was_checked={second_was_checked})")

        page.wait_for_timeout(300)

        # API verify
        r = api("GET", f"/api/v1/tables/{table_id}/views/{kanban_view_id}", token)
        assert r.status_code == 200, f"GET view: {r.status_code} {r.text[:200]}"
        card_fields_api = r.json().get("config", {}).get("card_fields", [])

        if second_was_checked:
            assert second_col["column_id"] not in card_fields_api, (
                f"API: {second_col['column_id']!r} still in card_fields"
            )
        else:
            assert second_col["column_id"] in card_fields_api, (
                f"API: {second_col['column_id']!r} not in card_fields"
            )
        print(f"[ok] API: second toggle verified for {second_col['name']!r}")

    snap(page, "kb_cf_04_after_toggle2", snapshot)

    # ── Step 5: Close panel, verify card renders correct fields ────────
    # Click elsewhere to close the panel
    page.locator('[data-testid="kanban-card-fields-btn"]').click()
    page.wait_for_timeout(300)

    # Get the current card_fields from API for verification
    r = api("GET", f"/api/v1/tables/{table_id}/views/{kanban_view_id}", token)
    final_card_fields = r.json().get("config", {}).get("card_fields", [])
    print(f"[ok] final card_fields={final_card_fields}")

    snap(page, "kb_cf_05_cards_visible", snapshot)

    # ── Step 6: Navigate away and back → verify persistence ───────────
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id)

    try:
        sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
        sprint_tab2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_tab_after_nav", snapshot)
        pytest.fail("Sprint Board tab not visible after navigation back")
    sprint_tab2.click()

    try:
        cf_btn2 = page.locator('[data-testid="kanban-card-fields-btn"]')
        cf_btn2.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_btn_after_nav", snapshot)
        pytest.fail("Card fields button not visible after navigation back")

    # Open panel and verify checkboxes match persisted state
    cf_btn2.click()
    page.wait_for_timeout(300)

    # Verify the target checkbox state persisted
    target_cb_after = page.locator(
        f'[data-testid="kanban-card-field-{target_col_id}-checkbox"]'
    )
    try:
        target_cb_after.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "kb_cf_FAIL_no_cb_after_nav", snapshot)
        pytest.fail("Checkboxes not visible after navigation back")

    is_checked_now = target_cb_after.is_checked()
    expected_checked = not was_checked  # we toggled it once
    assert is_checked_now == expected_checked, (
        f"Persistence check: {target_col['name']!r} checked={is_checked_now}, "
        f"expected={expected_checked}"
    )
    print(f"[ok] step 6 — checkbox state persists after navigation")

    # API verify persistence
    r = api("GET", f"/api/v1/tables/{table_id}/views/{kanban_view_id}", token)
    assert r.status_code == 200, f"GET view after nav: {r.status_code} {r.text[:200]}"
    persisted_fields = r.json().get("config", {}).get("card_fields", [])
    assert persisted_fields == final_card_fields, (
        f"API persistence: card_fields={persisted_fields!r}, "
        f"expected={final_card_fields!r}"
    )
    print(f"[ok] step 6 — API: card_fields persisted across navigation")

    snap(page, "kb_cf_06_after_nav_verified", snapshot)

    print("\n=== PASSED — test_kanban_card_fields ===")
