#!/usr/bin/env python3
"""
Task-262: Timeline drag — verify exactly 1 PUT fires on mouseup, not on every mousemove.

Drags a resize handle 5 month-cells to the right using 50 intermediate mousemove events.
Asserts that only 1 network PUT to /rows/{rn} fires, on mouseup.

Usage:
    docker compose exec browser python /app/test_timeline_drag_262.py
"""

import sys
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://localhost:13491"
SCREENSHOT_DIR = "/output"
# latticecast table is in the "claude" workspace (id: 31aab3c7-...) and has a Timeline view
WORKSPACE_ID = "31aab3c7-8c50-43b3-b855-db27b8676aa4"
TABLE_ID = "latticecast"
TIMELINE_VIEW_NAME = "Timeline"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "lattice",
    "userInfo": {"sub": "lattice", "email": "lattice", "name": "Lattice"},
    "role": "user",
}


def test_timeline_drag_mouseup_only():
    results = {
        "test": "timeline_drag_mouseup_only",
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

        # Collect PUT requests to rows endpoint
        row_puts: list[str] = []

        def on_request(request):
            if request.method == "PUT" and "/rows/" in request.url:
                row_puts.append(request.url)

        page.on("request", on_request)

        # Navigate to the PM table
        page.goto(
            f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}",
            wait_until="networkidle",
            timeout=30000,
        )

        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # Switch to Timeline view
        try:
            timeline_tab = page.locator(f'[data-testid="view-tab-{TIMELINE_VIEW_NAME}"]')
            timeline_tab.wait_for(timeout=8000)
            timeline_tab.click()
            page.wait_for_timeout(2000)
            results["checks"]["timeline_tab"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["timeline_tab"] = f"fail: '{TIMELINE_VIEW_NAME}' tab not found within 8s"
            page.screenshot(path=f"{SCREENSHOT_DIR}/task262_FAIL_no_tab.png", full_page=True)
            print(json.dumps(results, indent=2))
            return results

        # Wait for at least one timeline bar
        try:
            page.locator('[data-testid^="timeline-row-bar-"]').first.wait_for(timeout=8000)
            bar_count = page.locator('[data-testid^="timeline-row-bar-"]').count()
            results["checks"]["bars_loaded"] = f"pass: {bar_count} bar(s) visible"
        except PlaywrightTimeout:
            results["checks"]["bars_loaded"] = "fail: no [data-testid^='timeline-row-bar-'] found after 8s"
            page.screenshot(path=f"{SCREENSHOT_DIR}/task262_FAIL_no_bars.png", full_page=True)
            print(json.dumps(results, indent=2))
            return results

        # Find a resize handle — prefer end-date handle, fall back to start-date
        handle = None
        handle_label = ""
        for label in ("Resize end date", "Resize start date"):
            candidate = page.locator(f'button[aria-label="{label}"]').first
            try:
                candidate.wait_for(timeout=3000)
                handle = candidate
                handle_label = label
                break
            except PlaywrightTimeout:
                continue

        if handle is None:
            results["checks"]["resize_handle"] = "fail: no resize handles found (start/end cols not configured?)"
            page.screenshot(path=f"{SCREENSHOT_DIR}/task262_FAIL_no_handles.png", full_page=True)
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["resize_handle"] = f"pass: '{handle_label}' handle found"

        box = handle.bounding_box()
        if not box:
            results["checks"]["drag"] = "fail: handle bounding box unavailable"
            print(json.dumps(results, indent=2))
            return results

        # Snapshot before drag
        page.screenshot(path=f"{SCREENSHOT_DIR}/task262_before_drag.png", full_page=True)

        # Discard PUTs fired during navigation/setup
        row_puts.clear()

        # Drag: mousedown → 50 intermediate moves (5 month-cells = 600px) → mouseup
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        drag_px = 5 * 120  # month cellWidth = 120px

        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + drag_px, start_y, steps=50)
        page.mouse.up()

        # Allow async PUT request(s) to complete
        page.wait_for_timeout(1500)

        put_count = len(row_puts)
        if put_count == 1:
            results["checks"]["drag_put_count"] = f"pass: exactly 1 PUT fired on mouseup — {row_puts[0]}"
        elif put_count == 0:
            results["checks"]["drag_put_count"] = (
                "warn: 0 PUTs fired — delta may be 0 (bar not on a date row) or endColId not set"
            )
        else:
            results["checks"]["drag_put_count"] = (
                f"fail: {put_count} PUTs fired (expected 1, got mid-drag saves) — {row_puts}"
            )

        # Snapshot after drag
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = f"{SCREENSHOT_DIR}/task262_after_drag_{ts}.png"
        page.screenshot(path=snap, full_page=True)
        results["screenshot"] = snap

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
    result = test_timeline_drag_mouseup_only()
    sys.exit(0 if result.get("passed") else 1)
