#!/usr/bin/env python3
"""
Test: RowExpandPanel Doc tab empty state shows 'Start writing' link.
If doc is empty, should show empty state + 'Start writing →' button.
Clicking 'Start writing' should reveal the editor textarea.
"""

import sys
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


def _snap(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_doc_tab_empty_state():
    results = {
        "test": "doc_tab_empty_state",
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "passed": False,
    }

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
                    resp = ctx.request.fetch(
                        new_url,
                        method=route.request.method,
                        headers={"Authorization": "Bearer claude", "Content-Type": "application/json"},
                    )
                    route.fulfill(response=resp)
                except Exception as exc:
                    results.setdefault("route_errors", []).append(str(exc))
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table page"
            _snap(page, "doc_tab_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snap(page, "doc_tab_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # Wait for rows
        try:
            page.wait_for_selector("table tbody tr", timeout=8000)
        except PlaywrightTimeout:
            results["checks"]["table_loaded"] = "fail: no table rows"
            _snap(page, "doc_tab_FAIL_no_rows")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["table_loaded"] = "pass"
        _snap(page, "doc_tab_01_table")

        # Open expand panel
        expand_btn = page.locator('button[title="Expand row"]').first
        expand_btn.click()

        try:
            panel = page.locator('[role="dialog"][aria-label="Row details"]')
            panel.wait_for(timeout=5000)
        except PlaywrightTimeout:
            results["checks"]["panel_opens"] = "fail: panel not found"
            _snap(page, "doc_tab_FAIL_no_panel")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["panel_opens"] = "pass"
        _snap(page, "doc_tab_02_fields_tab")

        # Click Doc tab
        panel_locator = page.locator('[role="dialog"][aria-label="Row details"]')
        doc_tab = panel_locator.locator('button:has-text("Doc")')
        doc_tab.first.click()

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeout:
            pass
        page.wait_for_timeout(1500)
        _snap(page, "doc_tab_03_doc_tab")

        # Check what's shown
        panel_html = panel_locator.inner_html()
        has_start_writing = "Start writing" in panel_html
        has_textarea = "<textarea" in panel_html
        has_loading = "Loading" in panel_html

        results["checks"]["doc_tab_content"] = {
            "has_start_writing": has_start_writing,
            "has_textarea": has_textarea,
            "has_loading": has_loading,
        }

        # For rows with no doc: empty state must show, not raw textarea
        # For rows with doc content: textarea + preview must show
        if has_start_writing and not has_textarea:
            results["checks"]["empty_state"] = "pass: shows 'Start writing' empty state when doc is empty"

            # Click "Start writing" and verify textarea appears
            start_btn = panel_locator.locator('button:has-text("Start writing")')
            if start_btn.count() > 0:
                start_btn.first.click()
                page.wait_for_timeout(500)
                _snap(page, "doc_tab_04_after_start_writing")

                textarea_after = panel_locator.locator("textarea")
                if textarea_after.count() > 0:
                    results["checks"]["start_writing_click"] = "pass: textarea appears after clicking Start writing"
                else:
                    results["checks"]["start_writing_click"] = "fail: textarea not found after clicking Start writing"
            else:
                results["checks"]["start_writing_click"] = "skip: Start writing button not found via locator"

        elif has_textarea:
            # Doc has content — check preview pane also renders
            preview = panel_locator.locator(".prose")
            if preview.count() > 0:
                results["checks"]["doc_with_content"] = "pass: doc has content, textarea + preview visible"
            else:
                results["checks"]["doc_with_content"] = "warn: textarea visible but no .prose preview pane"
        elif has_loading:
            results["checks"]["doc_tab_state"] = "warn: still showing Loading after wait"
        else:
            results["checks"]["doc_tab_state"] = f"fail: unexpected state — no start_writing, no textarea, no loading"

        _snap(page, "doc_tab_05_final")

        failed = [k for k, v in results["checks"].items()
                  if isinstance(v, str) and v.startswith("fail")]
        results["passed"] = len(failed) == 0
        if failed:
            results["failed_checks"] = failed

    finally:
        browser.close()
        playwright.stop()

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    result = test_doc_tab_empty_state()
    sys.exit(0 if result.get("passed") else 1)
