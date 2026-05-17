#!/usr/bin/env python3
"""
E2E test: task-47 — rename workspace propagates to URL

Verifies:
  1. Setup: create workspace via API.
  2. UI: navigate to workspace, open settings, rename.
  3. UI: URL updates to new workspace name after rename.
  4. BE: GET /workspaces confirms new name persists.
  5. UI: navigate away and back — new URL still resolves.
  6. UI: duplicate rename attempt shows error.
  7. Teardown: DELETE workspace via API.

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_workspace_rename.py [--snapshot]
"""

import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
SCREENSHOT_DIR = "/output"

USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-rename-{SUFFIX}"
WS_NEW_NAME = f"ws-renamed-{SUFFIX}"


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

    # ── Setup: create workspace via API ──────────────────────────────────────
    print(f"[1] Setup: create workspace '{WS_NAME}'")
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_id = ws_data["workspace_id"]
    print(f"    workspace_id={ws_id}")

    # ── Playwright ───────────────────────────────────────────────────────────
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, USER, role="admin")

        # ── Step 2: Navigate to workspace ────────────────────────────────────
        print(f"[2] Navigate to /{WS_NAME}/")
        page.goto(f"{BASE}/{WS_NAME}/", wait_until="networkidle")
        if "/login" in page.url:
            fatal("Redirected to /login — auth failed")
        snap(page, "t47_01_workspace_page")

        # ── Step 3: Open settings and rename ─────────────────────────────────
        print(f"[3] Rename workspace to '{WS_NEW_NAME}' via settings dialog")
        settings_btn = page.get_by_test_id("ws-settings-btn")
        settings_btn.wait_for(state="visible", timeout=10000)
        settings_btn.click()

        rename_input = page.get_by_test_id("ws-rename-input")
        rename_input.wait_for(state="visible", timeout=5000)
        rename_input.fill(WS_NEW_NAME)
        snap(page, "t47_02_rename_filled")

        save_btn = page.get_by_test_id("ws-settings-save")
        save_btn.click()

        # ── Step 4: UI — verify URL updated to new name ─────────────────────
        print("[4] Verify URL contains new workspace name")
        page.wait_for_url(f"**/{WS_NEW_NAME}/**", timeout=10000)
        assert f"/{WS_NEW_NAME}/" in page.url, f"Expected '/{WS_NEW_NAME}/' in URL, got {page.url}"
        snap(page, "t47_03_url_updated")

        # ── Step 5: BE — verify rename persisted ─────────────────────────────
        print("[5] BE verify: workspace name updated in API")
        r = api("GET", "/api/v1/workspaces", token)
        assert r.status_code == 200
        ws_list = r.json()
        renamed = next((w for w in ws_list if w["workspace_id"] == ws_id), None)
        assert renamed is not None, f"Workspace {ws_id} not in API response"
        assert renamed["workspace_name"] == WS_NEW_NAME, (
            f"Expected name '{WS_NEW_NAME}', got '{renamed['workspace_name']}'"
        )

        # ── Step 6: UI — navigate away and back, URL still works ─────────────
        print("[6] Navigate away and back — new URL resolves")
        r_ws = api("GET", "/api/v1/workspaces", token)
        other_ws = next(
            (w for w in r_ws.json() if w["workspace_id"] != ws_id), None
        )
        if other_ws:
            page.goto(f"{BASE}/{other_ws['workspace_name']}/", wait_until="networkidle")
        else:
            page.goto(f"{BASE}/", wait_until="networkidle")

        page.goto(f"{BASE}/{WS_NEW_NAME}/", wait_until="networkidle")
        assert WS_NEW_NAME in page.url, (
            f"After re-navigation, expected '{WS_NEW_NAME}' in URL, got {page.url}"
        )
        snap(page, "t47_04_re_navigated")

        # ── Step 7: UI — old name no longer resolves ─────────────────────────
        print("[7] Old URL no longer resolves to workspace")
        page.goto(f"{BASE}/{WS_NAME}/", wait_until="networkidle")
        not_found = page.locator("text=Workspace not found")
        not_found.wait_for(state="visible", timeout=10000)
        snap(page, "t47_05_old_url_404")

        # ── Step 8: UI — duplicate rename shows error ────────────────────────
        print("[8] Verify duplicate name error in settings")
        page.goto(f"{BASE}/{WS_NEW_NAME}/", wait_until="networkidle")
        settings_btn2 = page.get_by_test_id("ws-settings-btn")
        settings_btn2.wait_for(state="visible", timeout=10000)
        settings_btn2.click()

        rename_input2 = page.get_by_test_id("ws-rename-input")
        rename_input2.wait_for(state="visible", timeout=5000)

        # Try to rename to an existing workspace name (use any other ws name)
        r_ws2 = api("GET", "/api/v1/workspaces", token)
        other_ws2 = next(
            (w for w in r_ws2.json() if w["workspace_id"] != ws_id), None
        )
        if other_ws2:
            rename_input2.fill(other_ws2["workspace_name"])
            page.get_by_test_id("ws-settings-save").click()

            error_el = page.get_by_test_id("ws-settings-error")
            error_el.wait_for(state="visible", timeout=5000)
            error_text = error_el.text_content() or ""
            assert "already exists" in error_text.lower(), (
                f"Expected 'already exists' error, got: {error_text}"
            )
            snap(page, "t47_06_duplicate_error")

            # Close dialog
            page.get_by_test_id("ws-settings-cancel").click()
        else:
            print("    (skipped — no other workspace for duplicate test)")

        # ── Teardown ─────────────────────────────────────────────────────────
        print("[9] Teardown: DELETE workspace via API")
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        assert r.status_code == 204, f"Delete failed: {r.status_code} {r.text[:200]}"

        r = api("GET", "/api/v1/workspaces", token)
        assert r.status_code == 200
        remaining = [w for w in r.json() if w["workspace_id"] == ws_id]
        assert len(remaining) == 0, f"Workspace still exists after delete: {remaining}"

        browser.close()

    print("PASS: e2e_test_workspace_rename")


if __name__ == "__main__":
    run()
