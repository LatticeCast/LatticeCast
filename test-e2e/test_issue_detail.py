#!/usr/bin/env python3
"""
Snapshot test: Issue Detail page — navigate to /<workspace>/<table>/<row_id>,
verify field badges + markdown rendered as HTML.

URL pattern: /<workspace_id>/<table_id>/<row_id>
The page shows:
  - Breadcrumb nav (user / workspace / table / row key)
  - Badge row: select/tags/text/number/date field values as rounded-full spans
  - Doc section: markdown rendered to HTML in a .prose container

Usage:
    docker compose exec browser python /app/test_issue_detail.py

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
# L-1 epic row — has all field types populated and a markdown doc
ROW_ID = "83c9440e-ac92-4f70-b6b7-5bb6abed6eb3"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}

# Expected badge fields (col types: select, tags, text, number, date shown as badges)
# We expect at least these to be visible as badges on the L-1 row
EXPECTED_BADGE_LABELS = ["Type", "Status", "Priority"]


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_issue_detail():
    results = {
        "test": "issue_detail_snapshot",
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

        # Navigate directly to the issue detail page
        detail_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}/{ROW_ID}"
        try:
            page.goto(detail_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading issue detail page"
            _snapshot(page, "L70_issue_detail_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: auth (page stayed on detail URL, not redirected to /login) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L70_issue_detail_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: page title contains the ticket key ---
        try:
            page.wait_for_function(
                "() => document.title && document.title.includes('L-1')",
                timeout=8000,
            )
            results["checks"]["page_title"] = f"pass: title = {page.title()!r}"
        except PlaywrightTimeout:
            title = page.title()
            results["checks"]["page_title"] = (
                f"warn: title {title!r} does not contain 'L-1'"
            )

        # --- Check 3: breadcrumb nav renders ---
        breadcrumb = page.locator("nav[aria-label='Breadcrumb']")
        if breadcrumb.count() > 0:
            breadcrumb_text = (breadcrumb.first.text_content() or "").strip()
            results["checks"]["breadcrumb"] = f"pass: breadcrumb text = {breadcrumb_text[:80]!r}"
        else:
            results["checks"]["breadcrumb"] = "fail: breadcrumb nav[aria-label='Breadcrumb'] not found"

        _snapshot(page, "L70_issue_detail_loaded")

        # --- Check 4: badge fields render ---
        # Badges are <span class="...rounded-full..."> with col.name: value inside
        # The page renders them as inline-flex rounded-full spans
        badge_spans = page.locator("span.rounded-full").all()
        badge_texts = [(s.text_content() or "").strip() for s in badge_spans]
        badge_texts = [t for t in badge_texts if t]

        found_labels = []
        for label in EXPECTED_BADGE_LABELS:
            if any(label in t for t in badge_texts):
                found_labels.append(label)

        if len(found_labels) >= 2:
            results["checks"]["field_badges"] = (
                f"pass: {len(found_labels)}/{len(EXPECTED_BADGE_LABELS)} expected badge labels found"
                f" — {found_labels}"
            )
        else:
            results["checks"]["field_badges"] = (
                f"fail: only {len(found_labels)}/{len(EXPECTED_BADGE_LABELS)} expected badge labels found"
                f" — found badges: {badge_texts[:10]}"
            )

        _snapshot(page, "L70_issue_detail_badges")

        # --- Check 5: doc section container renders ---
        doc_section = page.locator("div.rounded-xl.border")
        if doc_section.count() > 0:
            results["checks"]["doc_section"] = "pass: doc section container found"
        else:
            results["checks"]["doc_section"] = "fail: doc section container not found"

        # --- Check 6: markdown rendered as HTML in .prose container ---
        # The page renders docPreview via {@html docPreview} inside a .prose div
        try:
            prose = page.locator("div.prose")
            prose.wait_for(timeout=8000)
            prose_html = prose.first.inner_html()
            # Markdown headings become <h1>/<h2>, lists become <ul>/<li>
            has_html_tags = any(tag in prose_html for tag in ["<h1", "<h2", "<h3", "<ul", "<li", "<p"])
            if has_html_tags:
                results["checks"]["markdown_rendered"] = (
                    f"pass: .prose contains rendered HTML tags"
                )
            else:
                results["checks"]["markdown_rendered"] = (
                    f"warn: .prose found but no HTML block tags detected — html={prose_html[:200]!r}"
                )
        except PlaywrightTimeout:
            # Doc may still be loading or empty; check if "No doc yet" shows
            no_doc = page.locator("text=No doc yet")
            if no_doc.count() > 0:
                results["checks"]["markdown_rendered"] = "warn: doc is empty (no doc yet placeholder)"
            else:
                results["checks"]["markdown_rendered"] = "fail: .prose not found and no loading state within 8s"

        _snapshot(page, "L70_issue_detail_doc")

        # --- Check 7: Edit / Preview toggle button present ---
        edit_btn = page.locator("button:has-text('Edit'), button:has-text('Preview')")
        if edit_btn.count() > 0:
            btn_text = (edit_btn.first.text_content() or "").strip()
            results["checks"]["edit_toggle"] = f"pass: edit/preview toggle button = {btn_text!r}"
        else:
            results["checks"]["edit_toggle"] = "fail: Edit/Preview toggle button not found"

        # --- Check 8: back link to table /<workspace>/<table> present ---
        back_link = page.locator(f"a[href='/{WORKSPACE_ID}/{TABLE_ID}']")
        if back_link.count() > 0:
            results["checks"]["back_link"] = "pass: link back to table found in breadcrumb"
        else:
            results["checks"]["back_link"] = "warn: breadcrumb link to table not found"

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L70_issue_detail_{ts}")
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
    result = test_issue_detail()
    sys.exit(0 if result.get("passed") else 1)
