#!/usr/bin/env python3
"""
Snapshot test: CRM dashboard — 5 widgets populated.

Steps:
  1. Seed: GET workspace for 'lattice' user → POST /template/crm → POST 5 deal rows
  2. Navigate to /<workspace_id>/<table_id>?view=Sales+Dashboard with auth injected
  3. Screenshot → /output/crm_dashboard.png

Usage:
    docker compose exec browser python3 /app/snapshot_crm.py

Networking: browser container uses network_mode: host.
  - Frontend JS (baked at build time) targets localhost:13491.
  - We intercept API calls and forward to lattice-cast:13491 on the Docker network.
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

API = "http://localhost:13491/api/v1"
BASE_URL = "http://localhost:13491"
SCREENSHOT_DIR = "/output"
USER = "lattice"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": USER,
    "userInfo": {"sub": USER, "email": USER, "name": "Lattice"},
    "role": "user",
}


def _call(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {USER}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read()
        return json.loads(body) if body.strip() else None

DEALS = [
    {"title": "Acme Corp", "stage": "lead",      "value": 12000, "owner": "Alice", "close_date": "2026-06-01"},
    {"title": "Globex Inc", "stage": "qualified", "value": 45000, "owner": "Bob",   "close_date": "2026-05-15"},
    {"title": "Initech",    "stage": "proposal",  "value": 30000, "owner": "Alice", "close_date": "2026-05-30"},
    {"title": "Hooli",      "stage": "won",        "value": 80000, "owner": "Carol", "close_date": "2026-04-20"},
    {"title": "Pied Piper", "stage": "lost",       "value": 25000, "owner": "Bob",   "close_date": "2026-04-10"},
]


def seed():
    """Create CRM table and insert 5 deals. Returns (workspace_id, table_id)."""
    # 1. Get workspace
    workspaces = _call("GET", "/workspaces")
    if not workspaces:
        raise RuntimeError("No workspaces found for user 'lattice'")
    workspace_id = workspaces[0]["workspace_id"]

    # 2. Create CRM template — table_id "deals" (lowercase, matches LQL table("deals"))
    table_id = "deals"
    # Delete existing table so we get fresh LQL (re-create on each run is idempotent for tests)
    try:
        _call("DELETE", f"/tables/{table_id}")
    except urllib.error.HTTPError:
        pass  # table may not exist yet

    table = _call("POST", "/tables/template/crm", {"table_id": table_id, "workspace_id": workspace_id})

    # 3. Extract column IDs by name
    columns = table.get("columns", [])
    col_by_name = {c["name"]: c["column_id"] for c in columns}

    # 4. Seed 5 deals
    for deal in DEALS:
        row_data = {}
        if "Title" in col_by_name:
            row_data[col_by_name["Title"]] = deal["title"]
        if "Stage" in col_by_name:
            row_data[col_by_name["Stage"]] = deal["stage"]
        if "Value" in col_by_name:
            row_data[col_by_name["Value"]] = deal["value"]
        if "Owner" in col_by_name:
            row_data[col_by_name["Owner"]] = deal["owner"]
        if "Close Date" in col_by_name:
            row_data[col_by_name["Close Date"]] = deal["close_date"]
        _call("POST", f"/tables/{table_id}/rows", {"row_data": row_data})

    return workspace_id, table_id


def snapshot(workspace_id: str, table_id: str) -> dict:
    results = {
        "test": "crm_dashboard_snapshot",
        "timestamp": datetime.now().isoformat(),
        "workspace_id": workspace_id,
        "table_id": table_id,
        "checks": {},
        "passed": False,
    }

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        # Inject auth before any page script runs
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        # Forward API calls — both localhost and lattice-cast hostnames map to the same nginx
        def handle_route(route):
            url = route.request.url
            if "localhost:13491/api" in url or "lattice-cast:13491/api" in url:
                new_url = url.replace("localhost:13491", "localhost:13491").replace(
                    "lattice-cast:13491", "localhost:13491"
                )
                try:
                    resp = ctx.request.fetch(
                        new_url,
                        method=route.request.method,
                        headers={"Authorization": f"Bearer {USER}", "Content-Type": "application/json"},
                        data=route.request.post_data,
                    )
                    route.fulfill(response=resp)
                except Exception as exc:
                    results.setdefault("route_errors", []).append(str(exc))
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        target_url = f"{BASE_URL}/{workspace_id}/{table_id}?view=Sales+Dashboard"
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading dashboard page"
            page.screenshot(path=f"{SCREENSHOT_DIR}/crm_dashboard_FAIL_timeout.png")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # Check: not redirected to login
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            page.screenshot(path=f"{SCREENSHOT_DIR}/crm_dashboard_FAIL_auth.png")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # Wait for dashboard grid to appear
        try:
            page.locator('[data-testid="dashboard-grid"]').wait_for(timeout=10000)
            results["checks"]["dashboard_grid"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["dashboard_grid"] = "fail: dashboard-grid not found within 10s"
            page.screenshot(path=f"{SCREENSHOT_DIR}/crm_dashboard_FAIL_grid.png")
            print(json.dumps(results, indent=2))
            return results

        # Extra wait for widget data to load
        page.wait_for_timeout(3000)

        # Check all 5 widgets are present
        WIDGET_IDS = ["pipeline_value", "by_stage", "by_owner", "won_value", "recent"]
        missing = []
        for wid in WIDGET_IDS:
            el = page.locator(f'[data-testid="dashboard-widget-{wid}"]')
            if el.count() == 0:
                missing.append(wid)
        if missing:
            results["checks"]["widgets"] = f"fail: missing widgets {missing}"
        else:
            results["checks"]["widgets"] = f"pass: all 5 widgets present"

        # Final screenshot
        screenshot_path = f"{SCREENSHOT_DIR}/crm_dashboard.png"
        page.screenshot(path=screenshot_path, full_page=True)
        results["screenshot"] = screenshot_path

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
    print("Seeding CRM data...", flush=True)
    workspace_id, table_id = seed()
    print(f"workspace={workspace_id}  table={table_id}", flush=True)

    print("Taking snapshot...", flush=True)
    result = snapshot(workspace_id, table_id)
    sys.exit(0 if result.get("passed") else 1)
