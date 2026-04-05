#!/usr/bin/env python3
"""
Snapshot test: Kanban sort dropdown — verify sort controls are visible in config bar.
"""

import json
from playwright.sync_api import sync_playwright

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


def test_kanban_sort():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )
        page = ctx.new_page()

        def handle_route(route):
            url = route.request.url
            if "localhost:13491/api" in url:
                new_url = url.replace("localhost:13491", "lattice-cast:13491")
                try:
                    post_data = route.request.post_data
                    fetch_kwargs = {
                        "method": route.request.method,
                        "headers": {"Authorization": "Bearer claude", "Content-Type": "application/json"},
                    }
                    if post_data:
                        fetch_kwargs["data"] = post_data
                    resp = ctx.request.fetch(new_url, **fetch_kwargs)
                    route.fulfill(response=resp)
                except Exception as exc:
                    print(f"Route error: {exc}")
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        page.goto(table_url, wait_until="networkidle", timeout=30000)
        print("URL after goto:", page.url)

        if "/login" in page.url:
            page.screenshot(path=f"{SCREENSHOT_DIR}/144_kanban_sort_fail_auth.png")
            print("FAIL: redirected to login")
            return

        # Click Sprint Board tab
        sprint_tab = page.locator("button:has-text('Sprint Board')")
        sprint_tab.wait_for(timeout=8000)
        sprint_tab.click()
        page.wait_for_timeout(2000)

        page.screenshot(path=f"{SCREENSHOT_DIR}/144_kanban_sort_01_sprint_board.png", full_page=True)
        print("Screenshot 1: Sprint Board view")

        # Check for Sort by label in config bar
        sort_label = page.locator("text=Sort by")
        if sort_label.count() > 0:
            print("PASS: 'Sort by' label found in config bar")
        else:
            print("FAIL: 'Sort by' label not found")

        # Check for sort column dropdown (should have "— none —" option)
        selects = page.locator("select")
        count = selects.count()
        print(f"Found {count} select dropdowns (expected >= 2: group_by + sort_col)")

        page.screenshot(path=f"{SCREENSHOT_DIR}/144_kanban_sort_02_config_bar.png", full_page=False)
        print("Screenshot 2: Config bar (viewport)")

        # Select a sort column (e.g. first non-empty option)
        if count >= 2:
            sort_select = selects.nth(1)  # second select = sort col
            options = sort_select.locator("option").all_inner_texts()
            print(f"Sort column options: {options}")
            if len(options) > 1:
                sort_select.select_option(index=1)  # pick first actual column
                page.wait_for_timeout(1500)
                page.screenshot(path=f"{SCREENSHOT_DIR}/144_kanban_sort_03_after_sort_col.png", full_page=True)
                print("Screenshot 3: After selecting sort column (asc/desc should appear)")

                # Check for asc/desc dropdown
                selects_after = page.locator("select")
                count_after = selects_after.count()
                print(f"Selects after sort col chosen: {count_after} (expected >= 3 with dir dropdown)")

        print("DONE")

    finally:
        browser.close()
        playwright.stop()


test_kanban_sort()
