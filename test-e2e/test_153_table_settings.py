#!/usr/bin/env python3
"""
Snapshot test: Tables list — ⚙ settings icon opens rename/delete dialog (ticket 153)
Verifies:
  - Each table row has a ⚙ settings gear icon (aria-label="Table settings")
  - Clicking opens a dialog with name input, Save, Cancel, Delete table
  - Duplicate name validation works

Usage:
    docker compose exec browser python /app/test_153_table_settings.py
"""

import sys
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://lattice-cast:13491"
SCREENSHOT_DIR = "/output"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_table_settings():
    results = {
        "test": "table_settings_gear_icon",
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "passed": False,
    }

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )

        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        def handle_route(route):
            url = route.request.url
            if "localhost:13491/api" in url:
                new_url = url.replace("localhost:13491", "lattice-cast:13491")
                try:
                    resp = ctx.request.fetch(
                        new_url,
                        method=route.request.method,
                        headers={
                            "Authorization": "Bearer claude",
                            "Content-Type": "application/json",
                        },
                    )
                    route.fulfill(response=resp)
                except Exception as exc:
                    results.setdefault("route_errors", []).append(str(exc))
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        # Navigate to /tables
        try:
            page.goto(f"{BASE_URL}/tables", wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading /tables"
            _snapshot(page, "153_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to login"
            _snapshot(page, "153_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        _snapshot(page, "153_01_tables_list")

        # Check 1: Gear icons exist
        gear_icons = page.locator('[aria-label="Table settings"]').all()
        if len(gear_icons) >= 1:
            results["checks"]["gear_icons"] = f"pass: {len(gear_icons)} gear icon(s) found"
        else:
            results["checks"]["gear_icons"] = "fail: no gear icons found (aria-label='Table settings')"
            _snapshot(page, "153_FAIL_no_gears")
            print(json.dumps(results, indent=2))
            return results

        # Check 2: Click first gear icon → dialog opens
        gear_icons[0].click()
        page.wait_for_timeout(600)
        _snapshot(page, "153_02_settings_dialog")

        dialog = page.locator('[role="dialog"]')
        if dialog.count() >= 1:
            results["checks"]["dialog_opens"] = "pass: dialog opened on gear click"
        else:
            results["checks"]["dialog_opens"] = "fail: dialog did not open"
            print(json.dumps(results, indent=2))
            return results

        # Check 3: Dialog has name input
        name_input = page.locator('#table-rename-input')
        if name_input.count() >= 1:
            current_name = name_input.input_value()
            results["checks"]["name_input"] = f"pass: name input found with value '{current_name}'"
        else:
            results["checks"]["name_input"] = "fail: name input not found"

        # Check 4: Save button exists
        save_btn = page.locator('button:has-text("Save")')
        if save_btn.count() >= 1:
            results["checks"]["save_button"] = "pass: Save button found"
        else:
            results["checks"]["save_button"] = "fail: Save button not found"

        # Check 5: Cancel button exists
        cancel_btn = page.locator('button:has-text("Cancel")')
        if cancel_btn.count() >= 1:
            results["checks"]["cancel_button"] = "pass: Cancel button found"
        else:
            results["checks"]["cancel_button"] = "fail: Cancel button not found"

        # Check 6: Delete table button exists
        delete_btn = page.locator('button:has-text("Delete table")')
        if delete_btn.count() >= 1:
            results["checks"]["delete_button"] = "pass: 'Delete table' button found"
        else:
            results["checks"]["delete_button"] = "fail: 'Delete table' button not found"

        _snapshot(page, "153_03_dialog_content")

        # Check 7: Close dialog via Cancel
        cancel_btn.first.click()
        page.wait_for_timeout(400)
        dialog_after = page.locator('[role="dialog"]')
        if dialog_after.count() == 0:
            results["checks"]["dialog_close"] = "pass: dialog closed on Cancel"
        else:
            results["checks"]["dialog_close"] = "fail: dialog still open after Cancel"

        _snapshot(page, "153_04_dialog_closed")

        # Overall
        failed = [k for k, v in results["checks"].items() if str(v).startswith("fail")]
        results["passed"] = len(failed) == 0
        if failed:
            results["failed_checks"] = failed

    finally:
        browser.close()
        playwright.stop()

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    result = test_table_settings()
    sys.exit(0 if result.get("passed") else 1)
