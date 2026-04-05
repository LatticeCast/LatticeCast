#!/usr/bin/env python3
"""
Snapshot test: L-63 — dark mode tokens on TableGrid, KanbanBoard, TimelineView, RowExpandPanel
Captures screenshots in both light and dark mode to verify proper theme application.

Usage:
    docker compose exec browser python /app/test_l63_dark_theme.py
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
        page.screenshot(path=path, full_page=True)
        print(f"  Screenshot: {name}.png")
    except Exception as e:
        print(f"  Screenshot FAILED {name}: {e}")
    return path


def make_context(playwright, dark_mode: bool):
    browser = playwright.chromium.launch(headless=True)
    settings = {"darkMode": dark_mode}
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        ignore_https_errors=True,
    )
    ctx.add_init_script(
        f"""
        localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));
        localStorage.setItem('settings', JSON.stringify({json.dumps(settings)}));
        """
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
            except Exception:
                route.abort()
        else:
            route.continue_()

    page.route("**/*", handle_route)
    return browser, ctx, page


def run_screenshots():
    playwright = sync_playwright().start()

    for dark in [False, True]:
        mode = "dark" if dark else "light"
        print(f"\n=== {mode.upper()} MODE ===")

        browser, ctx, page = make_context(playwright, dark)
        try:
            table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
            page.goto(table_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
            _snapshot(page, f"L63_{mode}_01_table_grid")

            # Click Kanban view tab
            kanban_tab = page.locator("button:has-text('Sprint Board'), button:has-text('Kanban')").first
            if kanban_tab.is_visible():
                kanban_tab.click()
                page.wait_for_timeout(1000)
                _snapshot(page, f"L63_{mode}_02_kanban")

            # Click Timeline/Roadmap tab
            timeline_tab = page.locator("button:has-text('Roadmap'), button:has-text('Timeline')").first
            if timeline_tab.is_visible():
                timeline_tab.click()
                page.wait_for_timeout(1000)
                _snapshot(page, f"L63_{mode}_03_timeline")

            # Go back to Table view and open row expand panel
            table_tab = page.locator("button:has-text('Table')").first
            if table_tab.is_visible():
                table_tab.click()
                page.wait_for_timeout(1000)

            # Click the expand button on the first row
            expand_btn = page.locator("table tbody tr button[title='Expand row']").first
            if expand_btn.is_visible():
                expand_btn.click()
                page.wait_for_timeout(800)
                _snapshot(page, f"L63_{mode}_04_row_expand_fields")

                # Click Doc tab
                doc_tab = page.locator("button:has-text('Doc')").first
                if doc_tab.is_visible():
                    doc_tab.click()
                    page.wait_for_timeout(800)
                    _snapshot(page, f"L63_{mode}_05_row_expand_doc")

        except Exception as e:
            print(f"  Error in {mode} mode: {e}")
            _snapshot(page, f"L63_{mode}_ERROR")
        finally:
            browser.close()

    playwright.stop()
    print("\nAll screenshots saved to /output/")


if __name__ == "__main__":
    run_screenshots()
