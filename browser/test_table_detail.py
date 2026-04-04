#!/usr/bin/env python3
"""
Snapshot test: Table detail — Table view with rows
Verifies: columns render, sort/filter/group toolbar visible, data loaded

Usage:
    docker compose exec browser python /app/test_table_detail.py

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


def test_table_detail():
    results = {
        "test": "table_detail_snapshot",
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
        # The SPA reads loginInfo once on store initialisation; doing this
        # via add_init_script ensures the store starts authenticated.
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        # Forward API calls that the JS bundle directs to localhost:13491
        # to the real backend service (lattice-cast:13491 on Docker network).
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

        # Navigate directly to the table detail page
        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table detail page"
            _snapshot(page, "L66_table_detail_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: page stayed on table URL (not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L66_table_detail_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: Table grid renders (thead present) ---
        try:
            page.wait_for_selector("table thead", timeout=8000)
            results["checks"]["table_renders"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["table_renders"] = "fail: <table><thead> not found within 8s"
            _snapshot(page, "L66_table_detail_FAIL_no_thead")
            print(json.dumps(results, indent=2))
            return results

        # --- Check 3: Columns visible in thead ---
        th_cells = page.locator("table thead th").all()
        col_labels = []
        for th in th_cells:
            text = (th.text_content() or "").strip()
            # Skip the row-number "#" cell and the empty action cells
            if text and text != "#" and not text.startswith("("):
                col_labels.append(text)

        if len(col_labels) >= 1:
            results["checks"]["columns_render"] = (
                f"pass: {len(col_labels)} columns — {col_labels[:6]}"
            )
        else:
            results["checks"]["columns_render"] = "fail: no named column headers found"

        # --- Check 4: Sort / filter / group toolbar visible ---
        # TableToolbar renders buttons: Sort, Group, Hide Fields, Filter, Search…
        toolbar_buttons = page.locator(
            "button:has-text('Sort'), button:has-text('Filter'), "
            "button:has-text('Group'), button:has-text('Hide Fields')"
        )
        if toolbar_buttons.count() >= 2:
            btn_labels = [
                b.text_content().strip()
                for b in toolbar_buttons.all()[:8]
            ]
            results["checks"]["toolbar_visible"] = f"pass: {btn_labels}"
        else:
            results["checks"]["toolbar_visible"] = (
                "fail: expected ≥2 toolbar buttons (Sort/Filter/Group), found "
                + str(toolbar_buttons.count())
            )

        # --- Check 5: Data rows loaded ---
        tbody_rows = page.locator("table tbody tr").all()
        # Filter out the add-row '+' placeholder at the bottom
        data_rows = [
            r for r in tbody_rows
            if not (r.text_content() or "").strip().startswith("+")
        ]
        row_count = len(data_rows)
        if row_count >= 1:
            results["checks"]["data_loaded"] = f"pass: {row_count} data rows"
        else:
            results["checks"]["data_loaded"] = (
                f"warn: {row_count} data rows found (may be an empty table)"
            )

        # --- Check 6: View switcher tabs present ---
        view_tabs = page.locator("button:has-text('Table'), button:has-text('Sprint Board'), button:has-text('Roadmap'), button:has-text('Kanban'), button:has-text('Timeline')")
        if view_tabs.count() >= 1:
            tab_labels = [b.text_content().strip() for b in view_tabs.all()[:5]]
            results["checks"]["view_switcher"] = f"pass: {tab_labels}"
        else:
            results["checks"]["view_switcher"] = "warn: no view-switcher tabs found"

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L66_table_detail_{ts}")
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
    result = test_table_detail()
    sys.exit(0 if result.get("passed") else 1)
