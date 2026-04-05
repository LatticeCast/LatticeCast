#!/usr/bin/env python3
"""Snapshot dark theme tokens: TableGrid, KanbanBoard, TimelineView, RowExpandPanel."""

import json
import time
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

# Settings with dark mode enabled
SETTINGS_DARK = json.dumps({"darkMode": True})
SETTINGS_LIGHT = json.dumps({"darkMode": False})


def make_context(playwright, dark=False):
    browser = playwright.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1400, "height": 900},
        ignore_https_errors=True,
    )
    settings = SETTINGS_DARK if dark else SETTINGS_LIGHT
    ctx.add_init_script(
        f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        f"localStorage.setItem('settings', {json.dumps(settings)});"
    )

    def handle_route(route):
        url = route.request.url
        if "localhost:13491/api" in url:
            new_url = url.replace("localhost:13491", "lattice-cast:13491")
            try:
                resp = ctx.request.fetch(
                    new_url,
                    method=route.request.method,
                    headers=dict(route.request.headers),
                    data=route.request.post_data,
                )
                route.fulfill(response=resp)
            except Exception as e:
                route.abort()
        else:
            route.continue_()

    ctx.route("**/*", handle_route)
    return browser, ctx


def run():
    with sync_playwright() as p:
        for mode, dark in [("dark", True), ("light", False)]:
            browser, ctx = make_context(p, dark=dark)
            page = ctx.new_page()

            url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
            page.goto(url)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # TableGrid view
            page.screenshot(path=f"{SCREENSHOT_DIR}/{mode}_table_grid.png")
            print(f"Saved {mode}_table_grid.png")

            # Kanban view
            kanban = page.locator("button:has-text('Sprint Board')")
            if kanban.count() == 0:
                kanban = page.locator("button:has-text('Kanban')")
            if kanban.count() > 0:
                kanban.first.click()
                time.sleep(1)
                page.screenshot(path=f"{SCREENSHOT_DIR}/{mode}_kanban_board.png")
                print(f"Saved {mode}_kanban_board.png")

            # Timeline view
            timeline = page.locator("button:has-text('Roadmap')")
            if timeline.count() == 0:
                timeline = page.locator("button:has-text('Timeline')")
            if timeline.count() > 0:
                timeline.first.click()
                time.sleep(1)
                page.screenshot(path=f"{SCREENSHOT_DIR}/{mode}_timeline_view.png")
                print(f"Saved {mode}_timeline_view.png")

            # Back to Table, open RowExpandPanel
            table_btn = page.locator("button:has-text('Table')")
            if table_btn.count() > 0:
                table_btn.first.click()
                time.sleep(1)

            # Click first row number button
            row_num = page.locator("td button").first
            if row_num.count() > 0:
                row_num.click()
                time.sleep(1)
                page.screenshot(path=f"{SCREENSHOT_DIR}/{mode}_row_expand.png")
                print(f"Saved {mode}_row_expand.png")

            browser.close()

    print("All screenshots saved to /output (= .browser/)")


if __name__ == "__main__":
    run()
