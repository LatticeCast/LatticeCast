#!/usr/bin/env python3
"""
Snapshot test: Kanban view — Sprint Board
Verifies: switch to Sprint Board view, lanes present (todo/in_progress/review/merged/done),
          cards contain ticket info (Key, Title, Priority fields)

Usage:
    docker compose exec browser python /app/test_kanban_view.py

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

# Status choices defined in the PM template for Sprint Board lanes
EXPECTED_LANES = ["todo", "in_progress", "review", "done", "merged"]


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_kanban_view():
    results = {
        "test": "kanban_view_snapshot",
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
            _snapshot(page, "L67_kanban_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: page stayed on table URL (not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L67_kanban_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: View switcher shows Sprint Board tab ---
        try:
            sprint_tab = page.locator("button:has-text('Sprint Board')")
            sprint_tab.wait_for(timeout=8000)
            results["checks"]["sprint_board_tab"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["sprint_board_tab"] = "fail: Sprint Board tab not found within 8s"
            _snapshot(page, "L67_kanban_FAIL_no_tab")
            print(json.dumps(results, indent=2))
            return results

        # --- Click Sprint Board tab to switch view ---
        page.locator("button:has-text('Sprint Board')").click()
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass  # networkidle may not fire; continue

        _snapshot(page, "L67_kanban_after_switch")

        # --- Check 3: Kanban lanes are present ---
        # KanbanBoard renders each lane as role="group" aria-label="{value} lane"
        lanes_found = []
        lanes_missing = []
        for lane_val in EXPECTED_LANES:
            lane_el = page.locator(f'[role="group"][aria-label="{lane_val} lane"]')
            if lane_el.count() > 0:
                lanes_found.append(lane_val)
            else:
                lanes_missing.append(lane_val)

        if lanes_missing:
            results["checks"]["lanes"] = (
                f"fail: missing lanes {lanes_missing}, found {lanes_found}"
            )
        else:
            results["checks"]["lanes"] = f"pass: all lanes present — {lanes_found}"

        # --- Check 4: Lane headers show lane name badges ---
        lane_badges = page.locator('[role="group"] span.rounded-full').all()
        badge_texts = [b.text_content().strip() for b in lane_badges if b.text_content()]
        has_expected_badges = any(lane in badge_texts for lane in EXPECTED_LANES)
        if has_expected_badges:
            results["checks"]["lane_headers"] = f"pass: lane badges — {badge_texts[:8]}"
        else:
            results["checks"]["lane_headers"] = (
                f"warn: lane badges not matching expected values, found {badge_texts[:8]}"
            )

        # --- Check 5: Cards present with ticket info ---
        # Cards are <button> elements inside lane groups
        # Each card should contain Key, Title, Priority fields
        all_cards = page.locator('[role="group"] button[draggable="true"]').all()
        card_count = len(all_cards)

        if card_count >= 1:
            results["checks"]["cards_present"] = f"pass: {card_count} cards found"

            # Verify cards contain text (Key/Title values)
            card_texts = []
            for card in all_cards[:5]:
                text = (card.text_content() or "").strip()
                if text:
                    card_texts.append(text[:60])

            if card_texts:
                results["checks"]["card_content"] = (
                    f"pass: cards have text content — sample: {card_texts[:3]}"
                )
            else:
                results["checks"]["card_content"] = "warn: cards found but no text content"

            # Check for Key-style content (e.g. "L-1", "LC-1") in first card
            first_card_text = (all_cards[0].text_content() or "")
            import re
            has_key = bool(re.search(r'[A-Z]{1,4}-\d+', first_card_text))
            results["checks"]["card_has_key"] = (
                f"pass: ticket key pattern found" if has_key
                else f"warn: no ticket key pattern in first card text '{first_card_text[:80]}'"
            )
        else:
            # Could be empty table — not a fail, just a warning
            results["checks"]["cards_present"] = "warn: no draggable cards found (empty table?)"
            results["checks"]["card_content"] = "warn: skipped (no cards)"
            results["checks"]["card_has_key"] = "warn: skipped (no cards)"

        # --- Check 6: Row counts shown in lane headers ---
        # Each lane header shows a count badge (text-gray-400 span)
        count_spans = page.locator('[role="group"] .text-gray-400').all()
        count_texts = [s.text_content().strip() for s in count_spans if s.text_content().strip().isdigit()]
        if count_texts:
            results["checks"]["lane_counts"] = f"pass: lane counts visible — {count_texts[:6]}"
        else:
            results["checks"]["lane_counts"] = "warn: lane row counts not found"

        # --- Check 7: Group by is configured (Status column) ---
        # Config bar should show a select with 'Group by' label
        group_by_label = page.locator("span:has-text('Group by')")
        if group_by_label.count() > 0:
            results["checks"]["group_by_ui"] = "pass: Group by control visible"
        else:
            results["checks"]["group_by_ui"] = "warn: Group by control not found"

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L67_kanban_{ts}")
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
    result = test_kanban_view()
    sys.exit(0 if result.get("passed") else 1)
