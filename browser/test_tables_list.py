#!/usr/bin/env python3
"""
Snapshot test: Tables list page — login as lattice (Bearer claude)
Verifies:
  - workspace selector buttons visible
  - table list rendered
  - "From Template" (template gallery) button visible

Usage:
    docker compose exec browser python /app/test_tables_list.py

Note on networking:
    The frontend JS bundle has VITE_BACKEND_URL=http://localhost:13491 (baked at build time).
    Inside the browser container, localhost does not route to the app backend.
    We use Playwright route interception to forward /api/* calls from localhost:13491
    to lattice-cast:13491 (the nginx service on the Docker app-network).

    Auth is injected via context.add_init_script() so localStorage is populated
    before any page JS runs (avoids the SPA store initializing with null).
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


def test_tables_list():
    results = {
        "test": "tables_list_snapshot",
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

        # Inject auth into localStorage before any page script runs.
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        # Forward API calls from localhost:13491 to the real backend on Docker network.
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
        tables_url = f"{BASE_URL}/tables"
        try:
            page.goto(tables_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading /tables page"
            _snapshot(page, "L65_tables_list_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: page stayed on /tables (not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L65_tables_list_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: Workspace selector visible ---
        try:
            page.wait_for_selector("div.flex.flex-wrap button", timeout=8000)
            ws_buttons = page.locator("div.flex.flex-wrap button").all()
            ws_names = [b.text_content().strip() for b in ws_buttons if b.text_content().strip()]
            if ws_names:
                results["checks"]["workspace_selector"] = f"pass: {ws_names}"
            else:
                results["checks"]["workspace_selector"] = "warn: workspace selector found but no buttons"
        except PlaywrightTimeout:
            results["checks"]["workspace_selector"] = "fail: workspace selector not found within 8s"

        # --- Check 3: Table list rendered (at least one table card OR "No tables" message) ---
        table_cards = page.locator("div.rounded-2xl.bg-white.px-4.py-4").all()
        no_tables_msg = page.locator("text=No tables yet").count()
        if len(table_cards) >= 1:
            table_names = [c.text_content().strip()[:40] for c in table_cards[:5]]
            results["checks"]["table_list"] = f"pass: {len(table_cards)} table(s) — {table_names}"
        elif no_tables_msg > 0:
            results["checks"]["table_list"] = "pass: no tables in workspace (empty state shown)"
        else:
            results["checks"]["table_list"] = "fail: neither table cards nor empty-state found"

        # --- Check 4: "From Template" button visible ---
        template_btn = page.locator("button:has-text('From Template')")
        if template_btn.count() >= 1:
            results["checks"]["template_gallery_button"] = "pass: 'From Template' button found"
        else:
            results["checks"]["template_gallery_button"] = "fail: 'From Template' button not found"

        # --- Check 5: Page heading "Tables" visible ---
        heading = page.locator("h1:has-text('Tables')")
        if heading.count() >= 1:
            results["checks"]["page_heading"] = "pass: 'Tables' heading visible"
        else:
            results["checks"]["page_heading"] = "warn: 'Tables' heading not found"

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L65_tables_list_{ts}")
        results["screenshot"] = snap

        # Overall pass/fail
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
    result = test_tables_list()
    sys.exit(0 if result.get("passed") else 1)
