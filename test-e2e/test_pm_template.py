#!/usr/bin/env python3
"""
Snapshot test: Create PM from template — click "From Template", select PM Project,
fill in project name, submit, verify table created with all expected columns.

Flow:
  1. Navigate to /tables
  2. Click "From Template" button → modal opens with "New from Template" heading
  3. Type project name into the input
  4. Click "Create PM Project" button
  5. Wait for redirect to /<workspace>/<table_id>
  6. Verify the table view renders with all 13 PM columns

Expected PM columns (from _PM_COLUMNS in backend):
  Key, Title, Type, Status, Priority, Assignee,
  Start Date, Due Date, Estimate, Tags, Description, Doc, Parent

Usage:
    docker compose exec browser python /app/test_pm_template.py

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
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://lattice-cast:13491"
SCREENSHOT_DIR = "/output"
WORKSPACE_ID = "claude"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}

# All 13 columns the PM template creates
EXPECTED_PM_COLUMNS = [
    "Key", "Title", "Type", "Status", "Priority",
    "Assignee", "Start Date", "Due Date", "Estimate",
    "Tags", "Description", "Doc", "Parent",
]

# Unique project name to avoid collision across test runs
TEST_PROJECT_NAME = f"L71-Test-{int(time.time())}"


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_pm_template():
    results = {
        "test": "pm_template_snapshot",
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "passed": False,
    }

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )

        # Inject auth into localStorage before any page script runs.
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
                    fetch_kwargs: dict = {
                        "method": route.request.method,
                        "headers": {
                            "Authorization": "Bearer claude",
                            "Content-Type": "application/json",
                        },
                    }
                    if route.request.method not in ("GET", "HEAD"):
                        fetch_kwargs["data"] = route.request.post_data
                    resp = ctx.request.fetch(new_url, **fetch_kwargs)
                    route.fulfill(response=resp)
                except Exception as exc:
                    results.setdefault("route_errors", []).append(str(exc))
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        # --- Navigate to /tables ---
        tables_url = f"{BASE_URL}/tables"
        try:
            page.goto(tables_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading /tables page"
            _snapshot(page, "L71_pm_template_FAIL_timeout_tables")
            print(json.dumps(results, indent=2))
            return results

        results["tables_url"] = page.url

        # --- Check 1: auth (not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L71_pm_template_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: "From Template" button present ---
        from_template_btn = page.locator("button:has-text('From Template')")
        if from_template_btn.count() == 0:
            results["checks"]["from_template_button"] = "fail: 'From Template' button not found"
            _snapshot(page, "L71_pm_template_FAIL_no_button")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["from_template_button"] = "pass"

        # --- Click "From Template" ---
        from_template_btn.first.click()

        # --- Check 3: Modal opens with "New from Template" heading ---
        try:
            page.wait_for_selector("text=New from Template", timeout=5000)
            results["checks"]["modal_opens"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["modal_opens"] = "fail: modal did not open (no 'New from Template' heading)"
            _snapshot(page, "L71_pm_template_FAIL_no_modal")
            print(json.dumps(results, indent=2))
            return results

        # --- Check 4: PM Project option visible ---
        pm_project_label = page.locator("text=PM Project")
        if pm_project_label.count() >= 1:
            results["checks"]["pm_project_option"] = "pass"
        else:
            results["checks"]["pm_project_option"] = "fail: 'PM Project' option not found in modal"

        _snapshot(page, "L71_pm_template_modal_open")

        # --- Fill in project name ---
        name_input = page.locator("input[placeholder='Project name...']")
        if name_input.count() == 0:
            results["checks"]["name_input"] = "fail: project name input not found"
            _snapshot(page, "L71_pm_template_FAIL_no_input")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["name_input"] = "pass"

        name_input.first.fill(TEST_PROJECT_NAME)

        # --- Check 5: "Create PM Project" button is now enabled ---
        create_btn = page.locator("button:has-text('Create PM Project')")
        if create_btn.count() == 0:
            results["checks"]["create_button"] = "fail: 'Create PM Project' button not found"
            _snapshot(page, "L71_pm_template_FAIL_no_create_btn")
            print(json.dumps(results, indent=2))
            return results

        if create_btn.first.is_disabled():
            results["checks"]["create_button"] = "fail: 'Create PM Project' button is disabled after name entered"
            _snapshot(page, "L71_pm_template_FAIL_create_btn_disabled")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["create_button"] = "pass"

        _snapshot(page, "L71_pm_template_name_filled")

        # --- Click "Create PM Project" and wait for navigation ---
        with page.expect_navigation(timeout=20000):
            create_btn.first.click()

        results["after_create_url"] = page.url

        # --- Check 6: Redirected to table detail (URL matches /<workspace>/<table_id>) ---
        import re
        if re.search(r"/claude/[0-9a-f-]{36}$", page.url):
            results["checks"]["redirect_to_table"] = f"pass: {page.url}"
        else:
            results["checks"]["redirect_to_table"] = f"fail: unexpected URL after create: {page.url}"
            _snapshot(page, "L71_pm_template_FAIL_redirect")
            print(json.dumps(results, indent=2))
            return results

        # Wait for the table grid to load
        try:
            page.wait_for_selector("table thead", timeout=15000)
            results["checks"]["table_renders"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["table_renders"] = "fail: <table><thead> not found after create"
            _snapshot(page, "L71_pm_template_FAIL_no_thead")
            print(json.dumps(results, indent=2))
            return results

        # --- Check 7: All 13 PM columns visible in the header ---
        th_cells = page.locator("table thead th").all()
        visible_col_names = []
        for th in th_cells:
            text = (th.text_content() or "").strip()
            # Strip the type annotation "(text)", "(select)", etc.
            col_name = re.sub(r"\s*\(\w+\)\s*$", "", text).strip()
            if col_name and col_name != "#":
                visible_col_names.append(col_name)

        missing_cols = [c for c in EXPECTED_PM_COLUMNS if c not in visible_col_names]
        if not missing_cols:
            results["checks"]["all_pm_columns"] = (
                f"pass: all {len(EXPECTED_PM_COLUMNS)} PM columns present — {visible_col_names}"
            )
        else:
            results["checks"]["all_pm_columns"] = (
                f"fail: missing columns {missing_cols}; found {visible_col_names}"
            )

        # --- Check 8: View switcher shows Sprint Board and Roadmap ---
        view_tabs = page.locator(
            "button:has-text('Table'), button:has-text('Sprint Board'), button:has-text('Roadmap')"
        )
        if view_tabs.count() >= 3:
            tab_labels = [b.text_content().strip() for b in view_tabs.all()[:5]]
            results["checks"]["pm_views"] = f"pass: {tab_labels}"
        else:
            results["checks"]["pm_views"] = (
                f"warn: expected Table + Sprint Board + Roadmap tabs, found {view_tabs.count()}"
            )

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L71_pm_template_{ts}")
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
    result = test_pm_template()
    sys.exit(0 if result.get("passed") else 1)
