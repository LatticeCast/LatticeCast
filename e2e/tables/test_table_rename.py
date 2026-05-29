"""E2E test: rename table via settings dialog.

Verifies:
  1. Click table settings gear → dialog opens with current name pre-filled.
  2. Clear input, type new name, click Save → PUT /tables/{old_id} fires.
  3. API: GET /tables/{new_id} returns 200; GET /tables/{old_id} returns 404.
  4. UI: table card shows new name.
  5. Navigate to renamed table → grid renders.
  6. Conflict: rename to an existing table name → error shown in dialog.

Usage:
    docker compose exec -T e2e pytest tables/test_table_rename.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def test_table_rename(authed_page, workspace, admin_token, snapshot) -> None:
    page = authed_page
    token = admin_token
    ws_id, ws_name = workspace
    _TS = int(time.time())
    TABLE_A = f"rename-a-{_TS}"
    TABLE_B = f"rename-b-{_TS}"
    NEW_NAME = f"renamed-{_TS}"

    # ── Setup: create two tables ─────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_A, "workspace_id": ws_id})
    assert r.status_code == 201, f"create table A: {r.status_code} {r.text[:200]}"

    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_B, "workspace_id": ws_id})
    assert r.status_code == 201, f"create table B: {r.status_code} {r.text[:200]}"
    print(f"[setup] tables: {TABLE_A!r}, {TABLE_B!r}")

    # ── Step 1: Navigate to workspace, verify both cards visible ─────────
    print("[1] Navigate to workspace page")
    page.goto(f"{BASE}/{ws_name}/", wait_until="networkidle", timeout=20000)

    page.get_by_test_id(f"table-card-{TABLE_A}").wait_for(
        state="visible", timeout=10000
    )
    page.get_by_test_id(f"table-card-{TABLE_B}").wait_for(
        state="visible", timeout=5000
    )
    snap(page, "rename_01_workspace", snapshot)
    print("[ok] both table cards visible")

    # ── Step 2: Open table settings for TABLE_A ──────────────────────────
    print("[2] Open table settings dialog")
    settings_btn = page.get_by_test_id(f"table-settings-btn-{TABLE_A}")
    settings_btn.wait_for(state="visible", timeout=5000)
    settings_btn.click()

    rename_input = page.get_by_test_id("table-rename-input")
    rename_input.wait_for(state="visible", timeout=5000)

    pre_filled = rename_input.input_value()
    assert pre_filled == TABLE_A, \
        f"input pre-filled with {pre_filled!r}, expected {TABLE_A!r}"
    snap(page, "rename_02_dialog_open", snapshot)
    print(f"[ok] dialog open, input pre-filled with {TABLE_A!r}")

    # ── Step 3: Rename TABLE_A → NEW_NAME, wait for PUT ──────────────────
    print(f"[3] Rename {TABLE_A!r} → {NEW_NAME!r}")
    rename_input.click()
    rename_input.fill(NEW_NAME)

    with page.expect_response(
        lambda r: r.request.method == "PUT"
                  and f"/api/v1/tables/{TABLE_A}" in r.url,
        timeout=10000,
    ) as resp_info:
        page.get_by_test_id("table-rename-save-btn").click()

    put_resp = resp_info.value
    assert put_resp.status == 200, f"PUT returned {put_resp.status}"
    put_body = put_resp.json()
    assert put_body["table_id"] == NEW_NAME, \
        f"PUT response table_id={put_body['table_id']!r}, expected {NEW_NAME!r}"
    print(f"[ok] PUT /tables/{TABLE_A} → 200, table_id={NEW_NAME!r}")

    # Dialog should close
    try:
        rename_input.wait_for(state="hidden", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "rename_FAIL_dialog_not_closed", snapshot)
        pytest.fail("Settings dialog did not close after rename")

    snap(page, "rename_03_after_rename", snapshot)

    # ── Step 4: API verify — new name exists, old name gone ──────────────
    print("[4] API verify: new name exists, old name 404")
    r = api("GET", f"/api/v1/tables/{NEW_NAME}", token)
    assert r.status_code == 200, \
        f"GET /tables/{NEW_NAME}: {r.status_code} {r.text[:200]}"

    r = api("GET", f"/api/v1/tables/{TABLE_A}", token)
    assert r.status_code == 404, \
        f"GET /tables/{TABLE_A} should be 404, got {r.status_code}"
    print("[ok] API: new name 200, old name 404")

    # ── Step 5: UI verify — card shows new name ──────────────────────────
    print("[5] UI verify: card and sidebar updated")
    try:
        page.get_by_test_id(f"table-card-{NEW_NAME}").wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "rename_FAIL_no_new_card", snapshot)
        pytest.fail(f"table card {NEW_NAME!r} not visible after rename")

    assert page.get_by_test_id(f"table-card-{TABLE_A}").count() == 0, \
        f"old table card {TABLE_A!r} still visible after rename"
    print(f"[ok] UI: card {NEW_NAME!r} visible, old card gone")

    # ── Step 6: Navigate to renamed table → grid renders ─────────────────
    print("[6] Navigate to renamed table, verify grid")
    page.get_by_test_id(f"table-card-{NEW_NAME}").click()

    try:
        page.wait_for_url(f"**/{NEW_NAME}**", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "rename_FAIL_nav", snapshot)
        pytest.fail(f"navigation to renamed table failed: URL={page.url}")

    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=10000
        )
    except PlaywrightTimeout:
        snap(page, "rename_FAIL_grid", snapshot)
        pytest.fail("Schema tab not visible after navigating to renamed table")

    snap(page, "rename_05_grid", snapshot)
    print("[ok] renamed table grid renders")

    # ── Step 7: Conflict — rename TABLE_B to NEW_NAME (already taken) ────
    print(f"[7] Conflict: rename {TABLE_B!r} → {NEW_NAME!r} (should 409)")
    page.goto(f"{BASE}/{ws_name}/", wait_until="networkidle", timeout=15000)

    page.get_by_test_id(f"table-card-{TABLE_B}").wait_for(
        state="visible", timeout=10000
    )

    settings_btn_b = page.get_by_test_id(f"table-settings-btn-{TABLE_B}")
    settings_btn_b.wait_for(state="visible", timeout=5000)
    settings_btn_b.click()

    rename_input2 = page.get_by_test_id("table-rename-input")
    rename_input2.wait_for(state="visible", timeout=5000)
    rename_input2.fill(NEW_NAME)

    page.get_by_test_id("table-rename-save-btn").click()

    try:
        page.get_by_test_id("table-settings-error").wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        snap(page, "rename_FAIL_no_conflict_error", snapshot)
        pytest.fail("conflict error not shown when renaming to existing name")

    error_text = page.get_by_test_id("table-settings-error").text_content() or ""
    assert "already exists" in error_text.lower(), \
        f"expected 'already exists' in error, got: {error_text!r}"
    snap(page, "rename_06_conflict", snapshot)
    print(f"[ok] conflict error shown: {error_text!r}")

    # TABLE_B should still exist with old name
    r = api("GET", f"/api/v1/tables/{TABLE_B}", token)
    assert r.status_code == 200, \
        f"TABLE_B should still exist: {r.status_code}"
    print(f"[ok] API: {TABLE_B!r} unchanged after conflict")

    print("\n=== PASSED — test_table_rename ===")
