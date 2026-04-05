#!/usr/bin/env python3
"""
Snapshot test: View dropdown includes Table type
Verifies: "Add view" menu shows Table, Kanban, Timeline options
so users can create multiple table views with different configs.

Usage:
    docker compose exec browser python /app/test_view_dropdown.py
"""

import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://lattice-cast:13491"
SCREENSHOT_DIR = "/output"
WORKSPACE_ID = "claude"
TABLE_ID = "7e6821be-3de8-4e54-b0b6-05db91e5f797"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=False)
    except Exception:
        pass
    return path


def test_view_dropdown():
    results = {
        "test": "view_dropdown",
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
        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"

        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table page"
            _snapshot(page, "view_dropdown_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        _snapshot(page, "view_dropdown_01_table_loaded")

        # Find and click "Add view" button
        add_btn = page.query_selector('button[aria-label="Add view"]')
        if not add_btn:
            add_btn = page.get_by_text("Add view").first
        results["checks"]["add_view_btn_found"] = add_btn is not None

        if add_btn:
            add_btn.click()
            page.wait_for_timeout(400)
            _snapshot(page, "view_dropdown_02_menu_open")

            # Check all three view types appear
            menu_text = page.content()
            for vtype in ["Table", "Kanban", "Timeline"]:
                results["checks"][f"has_{vtype.lower()}"] = vtype in menu_text

        results["passed"] = all(results["checks"].values())

    finally:
        browser.close()
        playwright.stop()

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    test_view_dropdown()
