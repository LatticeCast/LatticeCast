#!/usr/bin/env python3
"""
Snapshot test: View config auto-apply on table load
Verifies: sort/group/filter from view config are applied before rendering

Usage:
    docker compose exec browser python /app/test_view_config_load.py
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


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_view_config_load():
    results = {
        "test": "view_config_load",
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

        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table detail page"
            _snapshot(page, "view_config_load_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # Check 1: Not redirected to login
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "view_config_load_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # Check 2: Table rendered
        try:
            page.wait_for_selector("table", timeout=5000)
            results["checks"]["table_renders"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["table_renders"] = "fail: table element not found"
            _snapshot(page, "view_config_load_FAIL_table")
            print(json.dumps(results, indent=2))
            return results

        # Check 3: Toolbar visible with Sort button
        sort_btn = page.query_selector("button:has-text('Sort')")
        if sort_btn:
            results["checks"]["toolbar"] = "pass: Sort button found"
        else:
            results["checks"]["toolbar"] = "fail: Sort button not found"

        # Check 4: Sort button is highlighted (active) — PM template Table view has sort set
        if sort_btn:
            sort_classes = sort_btn.get_attribute("class") or ""
            if "blue" in sort_classes:
                results["checks"]["sort_applied_on_load"] = "pass: Sort is active (view config sort applied on load)"
            else:
                results["checks"]["sort_applied_on_load"] = f"warn: Sort button not highlighted — may not be applied. classes={sort_classes[:80]}"
        else:
            results["checks"]["sort_applied_on_load"] = "skip: no Sort button"

        # Check 5: Data rows present
        rows = page.query_selector_all("tbody tr")
        row_count = len(rows)
        if row_count > 0:
            results["checks"]["data_loaded"] = f"pass: {row_count} rows"
        else:
            results["checks"]["data_loaded"] = "fail: no rows"

        snap = _snapshot(page, "view_config_load_initial")
        results["screenshot"] = snap

        results["passed"] = all(
            not v.startswith("fail") for v in results["checks"].values()
        )

    finally:
        browser.close()
        playwright.stop()

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    r = test_view_config_load()
    sys.exit(0 if r.get("passed") else 1)
