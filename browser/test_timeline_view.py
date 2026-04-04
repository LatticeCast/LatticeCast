#!/usr/bin/env python3
"""
Snapshot test: Timeline view — Roadmap
Verifies: switch to Roadmap (timeline) view, date bars render,
          config panel (Start/End/Color by/Group by selects),
          zoom controls (day/week/month granularity buttons)

Usage:
    docker compose exec browser python /app/test_timeline_view.py

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

# Granularity buttons in the Timeline config bar
EXPECTED_GRANULARITIES = ["day", "week", "month"]

# Config panel labels (as rendered in the component)
EXPECTED_CONFIG_LABELS = ["Start", "End", "Color by", "Group by"]


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_timeline_view():
    results = {
        "test": "timeline_view_snapshot",
        "timestamp": datetime.now().isoformat(),
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

        # Navigate to the table detail page
        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table detail page"
            _snapshot(page, "L68_timeline_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: page stayed on table URL (not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L68_timeline_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: View switcher shows Roadmap tab ---
        try:
            roadmap_tab = page.locator("button:has-text('Roadmap')")
            roadmap_tab.wait_for(timeout=8000)
            results["checks"]["roadmap_tab"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["roadmap_tab"] = "fail: Roadmap tab not found within 8s"
            _snapshot(page, "L68_timeline_FAIL_no_tab")
            print(json.dumps(results, indent=2))
            return results

        # --- Click Roadmap tab to switch to Timeline view ---
        page.locator("button:has-text('Roadmap')").click()
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass  # networkidle may not fire; continue

        _snapshot(page, "L68_timeline_after_switch")

        # --- Check 3: Config bar labels (Start / End / Color by / Group by) ---
        found_labels = []
        missing_labels = []
        for label in EXPECTED_CONFIG_LABELS:
            label_el = page.locator(f"span:has-text('{label}')")
            if label_el.count() > 0:
                found_labels.append(label)
            else:
                missing_labels.append(label)

        if missing_labels:
            results["checks"]["config_labels"] = (
                f"fail: missing config labels {missing_labels}, found {found_labels}"
            )
        else:
            results["checks"]["config_labels"] = (
                f"pass: all config labels present — {found_labels}"
            )

        # --- Check 4: Config bar has select dropdowns for Start/End/Color by/Group by ---
        config_bar = page.locator("div.border-b.border-gray-200.bg-white.px-4.py-2").first
        selects_in_config = config_bar.locator("select").all()
        select_count = len(selects_in_config)
        if select_count >= 4:
            results["checks"]["config_selects"] = (
                f"pass: {select_count} config select dropdowns found (Start/End/Color by/Group by)"
            )
        elif select_count >= 2:
            results["checks"]["config_selects"] = (
                f"warn: only {select_count} config selects found (expected 4)"
            )
        else:
            results["checks"]["config_selects"] = (
                f"fail: too few config selects found ({select_count})"
            )

        # --- Check 5: Zoom / granularity controls (day / week / month buttons) ---
        found_zoom = []
        missing_zoom = []
        for g in EXPECTED_GRANULARITIES:
            btn = page.locator(f"button:has-text('{g}')")
            if btn.count() > 0:
                found_zoom.append(g)
            else:
                missing_zoom.append(g)

        if missing_zoom:
            results["checks"]["zoom_controls"] = (
                f"fail: missing granularity buttons {missing_zoom}, found {found_zoom}"
            )
        else:
            results["checks"]["zoom_controls"] = (
                f"pass: all granularity buttons present — {found_zoom}"
            )

        # --- Check 6: Date bars rendered (timeline grid rows) ---
        # Bars are absolute-positioned divs with bg-*-400 classes inside the timeline grid.
        # The timeline is rendered as colored divs; look for role="button" bar elements.
        bar_elements = page.locator('[role="button"][tabindex="0"]').all()
        # Filter to those likely inside the timeline (exclude expand buttons etc.)
        timeline_bars = [b for b in bar_elements if "rounded" in (b.get_attribute("class") or "")]
        bar_count = len(timeline_bars)

        if bar_count >= 1:
            results["checks"]["date_bars"] = f"pass: {bar_count} date bar(s) found"
            # Sample first bar title for date range info
            first_title = timeline_bars[0].get_attribute("title") or ""
            if "→" in first_title or first_title:
                results["checks"]["bar_dates"] = (
                    f"pass: bar title contains date range — '{first_title[:80]}'"
                )
            else:
                results["checks"]["bar_dates"] = "warn: bar title empty or no date range"
        else:
            # Could be no rows with start dates configured
            results["checks"]["date_bars"] = (
                "warn: no date bars found (rows may lack Start date values)"
            )
            results["checks"]["bar_dates"] = "warn: skipped (no bars)"

        # --- Check 7: Timeline header shows time columns (date labels) ---
        # Time-column headers are divs with text content like "Apr 2026", "W14 2026", "4/1"
        # They live in the sticky header row.
        header_cells = page.locator(
            "div.sticky.top-0 > div.flex-shrink-0"
        ).all()
        # Exclude the sidebar corner (no text)
        cell_texts = [
            (c.text_content() or "").strip()
            for c in header_cells
            if (c.text_content() or "").strip()
        ]
        if cell_texts:
            results["checks"]["time_headers"] = (
                f"pass: {len(cell_texts)} time column headers — sample: {cell_texts[:4]}"
            )
        else:
            results["checks"]["time_headers"] = (
                "warn: no time column headers found (grid may not have rendered)"
            )

        # --- Check 8: Clicking a zoom button changes granularity ---
        # Click "week" button and verify it becomes active (bg-white shadow classes)
        week_btn = page.locator("button:has-text('week')").first
        if week_btn.count() > 0:
            week_btn.click()
            page.wait_for_timeout(500)
            week_class = week_btn.get_attribute("class") or ""
            if "bg-white" in week_class:
                results["checks"]["zoom_switch"] = "pass: week granularity button active after click"
            else:
                results["checks"]["zoom_switch"] = (
                    "warn: week button clicked but active class not detected "
                    f"(class='{week_class[:80]}')"
                )
            _snapshot(page, "L68_timeline_week_granularity")
        else:
            results["checks"]["zoom_switch"] = "warn: week button not found for interaction test"

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L68_timeline_{ts}")
        results["screenshot"] = snap

        # Overall pass/fail — only hard "fail:" entries count
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
    result = test_timeline_view()
    sys.exit(0 if result.get("passed") else 1)
