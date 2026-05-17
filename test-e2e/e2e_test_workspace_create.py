#!/usr/bin/env python3
"""
E2E test: task-45 — POST /workspaces (V17 SECURITY DEFINER)

Verifies:
  1. UI: click "+ New" button → modal appears → fill name → submit
  2. UI: navigates to the new workspace page
  3. BE: GET /workspaces lists the new workspace
  4. BE: GET /workspaces/{id}/members shows creator as owner
  5. UI: duplicate name → error message displayed in modal
  6. Teardown: DELETE /workspaces/{id}

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_workspace_create.py [--snapshot]
"""

import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, BROWSER_WS, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
SCREENSHOT_DIR = "/output"

USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-create-{SUFFIX}"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def run() -> None:
    # ── Auth ─────────────────────────────────────────────────────────────────
    print("[0] Login")
    token = login(USER)

    # Get existing workspace to navigate to (the "+ New" btn lives there)
    r = api("GET", "/api/v1/workspaces", token)
    if r.status_code != 200 or not r.json():
        fatal(f"Cannot list workspaces: {r.status_code} {r.text[:200]}")
    existing_ws = r.json()[0]["workspace_name"]

    # ── Playwright ───────────────────────────────────────────────────────────
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, USER, role="admin")

        # ── Step 1: Navigate to existing workspace ───────────────────────────
        print(f"[1] Navigate to /{existing_ws}/")
        page.goto(f"{BASE}/{existing_ws}/", wait_until="networkidle")
        if "/login" in page.url:
            fatal("Redirected to /login — auth failed")

        # Wait for "+ New" workspace button in the tab strip
        new_ws_btn = page.get_by_test_id("new-workspace-btn")
        new_ws_btn.wait_for(state="visible", timeout=10000)
        snap(page, "t45_01_workspace_page")

        # ── Step 2: Open modal and create workspace ──────────────────────────
        print(f"[2] Create workspace '{WS_NAME}' via modal")
        new_ws_btn.click()

        name_input = page.get_by_test_id("create-workspace-name-input")
        name_input.wait_for(state="visible", timeout=5000)
        name_input.fill(WS_NAME)
        snap(page, "t45_02_modal_filled")

        page.get_by_test_id("create-workspace-submit").click()

        # ── Step 3: UI — verify navigation to new workspace ──────────────────
        print("[3] Verify URL navigated to new workspace")
        page.wait_for_url(f"**/{WS_NAME}/**", timeout=10000)
        assert WS_NAME in page.url, f"Expected '{WS_NAME}' in URL, got {page.url}"
        snap(page, "t45_03_navigated")

        # ── Step 4: BE — verify workspace exists via API ─────────────────────
        print("[4] BE verify: workspace listed + creator is owner")
        r = api("GET", "/api/v1/workspaces", token)
        assert r.status_code == 200
        ws_list = r.json()
        created = next((w for w in ws_list if w["workspace_name"] == WS_NAME), None)
        assert created is not None, f"Workspace '{WS_NAME}' not in API response"
        ws_id = created["workspace_id"]

        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", token)
        assert r.status_code == 200
        members = r.json()
        owner = next((m for m in members if m["role"] == "owner"), None)
        assert owner is not None, "No owner found in workspace members"

        # ── Step 5: UI — duplicate name shows error ──────────────────────────
        print("[5] Verify duplicate name error in modal")
        new_ws_btn2 = page.get_by_test_id("new-workspace-btn")
        new_ws_btn2.wait_for(state="visible", timeout=5000)
        new_ws_btn2.click()

        name_input2 = page.get_by_test_id("create-workspace-name-input")
        name_input2.wait_for(state="visible", timeout=5000)
        name_input2.fill(WS_NAME)
        page.get_by_test_id("create-workspace-submit").click()

        error_el = page.get_by_test_id("create-workspace-error")
        error_el.wait_for(state="visible", timeout=5000)
        error_text = error_el.text_content() or ""
        assert "already exists" in error_text.lower() or "conflict" in error_text.lower(), (
            f"Expected duplicate error, got: {error_text}"
        )
        snap(page, "t45_05_duplicate_error")

        # Close modal
        page.get_by_test_id("create-workspace-cancel").click()

        # ── Teardown ─────────────────────────────────────────────────────────
        print("[6] Teardown: DELETE workspace via API")
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        assert r.status_code == 204, f"Delete failed: {r.status_code} {r.text[:200]}"

        # Verify deletion
        r = api("GET", "/api/v1/workspaces", token)
        assert r.status_code == 200
        remaining = [w for w in r.json() if w["workspace_name"] == WS_NAME]
        assert len(remaining) == 0, f"Workspace still exists after delete: {remaining}"

        browser.close()

    print("PASS: e2e_test_workspace_create")


if __name__ == "__main__":
    run()
