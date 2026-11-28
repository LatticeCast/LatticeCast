#!/usr/bin/env python3
"""
E2E test: task-47 — rename workspace propagates to URL

Verifies:
  1. Setup: create workspace via API.
  2. UI: navigate to workspace, open settings, rename.
  3. UI: URL updates to new workspace name after rename.
  4. BE: GET /workspaces confirms new name persists.
  5. UI: navigate away and back — new URL still resolves.
  6. UI: renaming onto a taken name is allowed and the newer one gets a -1 URL.
  7. Teardown: DELETE workspace via API.

Usage:
    docker compose exec -T e2e pytest workspace/test_rename.py -v [--snapshot]
"""

import re
import time

import pytest
from playwright.sync_api import expect

from e2e_base import BASE, api

SCREENSHOT_DIR = "/output"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_workspace_rename(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    ws_id, ws_name = workspace
    suffix = int(time.time()) % 100000
    ws_new_name = f"ws-renamed-{suffix}"

    # ── Step 2: Navigate to workspace ────────────────────────────────────
    print(f"[2] Navigate to /{ws_name}/")
    page.goto(f"{BASE}/{ws_name}/", wait_until="networkidle")
    if "/login" in page.url:
        pytest.fail("Redirected to /login — auth failed")
    snap(page, "t47_01_workspace_page", snapshot)

    # ── Step 3: Open settings and rename ─────────────────────────────────
    print(f"[3] Rename workspace to '{ws_new_name}' via settings dialog")
    settings_btn = page.get_by_test_id("ws-settings-btn")
    settings_btn.wait_for(state="visible", timeout=10000)
    settings_btn.click()

    rename_input = page.get_by_test_id("ws-rename-input")
    rename_input.wait_for(state="visible", timeout=5000)
    rename_input.fill(ws_new_name)
    snap(page, "t47_02_rename_filled", snapshot)

    save_btn = page.get_by_test_id("ws-settings-save")
    save_btn.click()

    # ── Step 4: UI — verify URL updated to new name ─────────────────────
    print("[4] Verify URL contains new workspace name")
    expect(page).to_have_url(re.compile(re.escape(ws_new_name)), timeout=10000)
    snap(page, "t47_03_url_updated", snapshot)

    # ── Step 5: BE — verify rename persisted ─────────────────────────────
    print("[5] BE verify: workspace name updated in API")
    r = api("GET", "/api/v1/workspaces", admin_token)
    assert r.status_code == 200
    ws_list = r.json()
    renamed = next((w for w in ws_list if w["workspace_id"] == ws_id), None)
    assert renamed is not None, f"Workspace {ws_id} not in API response"
    assert renamed["workspace_name"] == ws_new_name, (
        f"Expected name '{ws_new_name}', got '{renamed['workspace_name']}'"
    )

    # ── Step 6: UI — navigate away and back, URL still works ─────────────
    print("[6] Navigate away and back — new URL resolves")
    r_ws = api("GET", "/api/v1/workspaces", admin_token)
    other_ws = next(
        (w for w in r_ws.json() if w["workspace_id"] != ws_id), None
    )
    if other_ws:
        page.goto(f"{BASE}/{other_ws['workspace_name']}/", wait_until="networkidle")
    else:
        page.goto(f"{BASE}/", wait_until="networkidle")

    page.goto(f"{BASE}/{ws_new_name}/", wait_until="networkidle")
    assert ws_new_name in page.url, (
        f"After re-navigation, expected '{ws_new_name}' in URL, got {page.url}"
    )
    snap(page, "t47_04_re_navigated", snapshot)

    # ── Step 7: UI — old name no longer resolves ─────────────────────────
    print("[7] Old URL no longer resolves to workspace")
    page.goto(f"{BASE}/{ws_name}/", wait_until="networkidle")
    not_found = page.locator("text=Workspace not found")
    not_found.wait_for(state="visible", timeout=10000)
    snap(page, "t47_05_old_url_404", snapshot)

    # ── Step 8: UI — renaming onto a taken name is allowed; URL gets -1 ──
    print("[8] Rename a newer workspace to the same name: its URL takes -1")
    other_name = f"ws-twin-{suffix}"
    r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": other_name})
    assert r.status_code == 201, r.text[:200]
    other_id = r.json()["workspace_id"]
    try:
        page.goto(f"{BASE}/{other_name}/", wait_until="networkidle")
        page.get_by_test_id("ws-settings-btn").click()
        rename_input2 = page.get_by_test_id("ws-rename-input")
        rename_input2.wait_for(state="visible", timeout=5000)
        rename_input2.fill(ws_new_name)
        page.get_by_test_id("ws-settings-save").click()
        expect(page).to_have_url(re.compile(re.escape(f"{ws_new_name}-1") + "/?$"), timeout=10000)
        tab = page.get_by_test_id(f"workspace-tab-{other_id}")
        assert "bg-blue-600" in tab.get_attribute("class"), "the renamed workspace is not the open one"
        snap(page, "t47_06_duplicate_suffix", snapshot)
    finally:
        api("DELETE", f"/api/v1/workspaces/{other_id}", admin_token)

    print("PASS: test_workspace_rename")
