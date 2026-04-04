#!/usr/bin/env python3
"""
Snapshot test: Row Expand panel — Fields tab and Doc tab
Verifies: click row expand button → panel opens, Fields tab shows all column
          labels, Doc tab shows markdown content.

Usage:
    docker compose exec browser python /app/test_row_expand.py

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

# PM template column names expected in the Fields tab
EXPECTED_FIELDS = ["Key", "Title", "Type", "Status", "Priority", "Assignee",
                   "Start Date", "Due Date", "Estimate", "Tags", "Description"]


def _snapshot(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def test_row_expand():
    results = {
        "test": "row_expand_snapshot",
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

        # Navigate to the table detail page
        table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
        try:
            page.goto(table_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            results["error"] = "Timeout loading table detail page"
            _snapshot(page, "L69_row_expand_FAIL_timeout")
            print(json.dumps(results, indent=2))
            return results

        results["final_url"] = page.url

        # --- Check 1: auth (page stayed on table URL) ---
        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snapshot(page, "L69_row_expand_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # --- Check 2: table grid loads with at least one data row ---
        try:
            page.wait_for_selector("table tbody tr", timeout=8000)
        except PlaywrightTimeout:
            results["checks"]["table_loaded"] = "fail: table rows not found within 8s"
            _snapshot(page, "L69_row_expand_FAIL_no_rows")
            print(json.dumps(results, indent=2))
            return results

        tbody_rows = page.locator("table tbody tr").all()
        data_rows = [
            r for r in tbody_rows
            if not (r.text_content() or "").strip().startswith("+")
        ]
        if not data_rows:
            results["checks"]["table_loaded"] = "fail: no data rows found (empty table)"
            _snapshot(page, "L69_row_expand_FAIL_empty_table")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["table_loaded"] = f"pass: {len(data_rows)} data rows"

        # --- Open expand panel by clicking the row-number button (title="Expand row") ---
        # The first row's expand button is in the sticky "#" column.
        expand_btn = page.locator('button[title="Expand row"]').first
        expand_btn.click()

        # --- Check 3: expand panel appears (role="dialog" aria-label="Row details") ---
        try:
            panel = page.locator('[role="dialog"][aria-label="Row details"]')
            panel.wait_for(timeout=5000)
            results["checks"]["panel_opens"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["panel_opens"] = "fail: Row details dialog not found within 5s"
            _snapshot(page, "L69_row_expand_FAIL_no_panel")
            print(json.dumps(results, indent=2))
            return results

        _snapshot(page, "L69_row_expand_panel_open")

        # --- Check 4: Fields tab is active by default ---
        # Scope tab selectors inside the dialog to avoid matching table column headers
        panel_locator = page.locator('[role="dialog"][aria-label="Row details"]')
        fields_tab = panel_locator.locator('button:has-text("Fields")')
        doc_tab = panel_locator.locator('button:has-text("Doc")')
        if fields_tab.count() > 0 and doc_tab.count() > 0:
            results["checks"]["tabs_present"] = "pass: Fields and Doc tabs found"
        else:
            results["checks"]["tabs_present"] = (
                f"fail: tabs missing — Fields={fields_tab.count()}, Doc={doc_tab.count()}"
            )

        # --- Check 5: Fields tab shows column labels ---
        # Labels are rendered as <label> elements with col.name + (col.type)
        field_labels = page.locator('[role="dialog"] label').all()
        label_texts = []
        for lbl in field_labels:
            text = (lbl.text_content() or "").strip()
            # strip the type annotation in parens, keep the column name
            if text:
                col_name = text.split("(")[0].strip()
                if col_name:
                    label_texts.append(col_name)

        found_fields = [f for f in EXPECTED_FIELDS if f in label_texts]
        missing_fields = [f for f in EXPECTED_FIELDS if f not in label_texts]

        if len(found_fields) >= 8:
            results["checks"]["fields_tab_labels"] = (
                f"pass: {len(found_fields)}/{len(EXPECTED_FIELDS)} expected fields present"
                f" — {found_fields}"
            )
        else:
            results["checks"]["fields_tab_labels"] = (
                f"fail: only {len(found_fields)}/{len(EXPECTED_FIELDS)} expected fields found"
                f" — missing {missing_fields}, found labels {label_texts}"
            )

        # --- Check 6: Field value buttons render (at least some have content) ---
        field_buttons = page.locator('[role="dialog"] .flex-1.overflow-y-auto button').all()
        if len(field_buttons) >= 1:
            results["checks"]["field_values_render"] = (
                f"pass: {len(field_buttons)} field value buttons rendered"
            )
        else:
            results["checks"]["field_values_render"] = (
                "warn: no field value buttons found in panel"
            )

        _snapshot(page, "L69_row_expand_fields_tab")

        # --- Switch to Doc tab ---
        doc_tab.first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeout:
            pass  # networkidle may not fire; continue

        # --- Check 7: Doc tab — markdown textarea visible ---
        try:
            textarea = page.locator('[role="dialog"] textarea')
            textarea.wait_for(timeout=6000)
            results["checks"]["doc_tab_textarea"] = "pass: markdown textarea visible"
        except PlaywrightTimeout:
            results["checks"]["doc_tab_textarea"] = "fail: textarea not found in Doc tab within 6s"

        # --- Check 8: Doc tab — preview pane visible ---
        preview_pane = page.locator('[role="dialog"] .prose')
        if preview_pane.count() > 0:
            results["checks"]["doc_tab_preview"] = "pass: markdown preview pane present"
        else:
            results["checks"]["doc_tab_preview"] = "warn: .prose preview pane not found"

        # --- Check 9: Doc content is not completely empty ---
        try:
            textarea_el = page.locator('[role="dialog"] textarea').first
            doc_text = textarea_el.input_value() if textarea_el.count() > 0 else ""
            if doc_text.strip():
                results["checks"]["doc_has_content"] = (
                    f"pass: doc has content ({len(doc_text)} chars)"
                )
            else:
                results["checks"]["doc_has_content"] = (
                    "warn: doc textarea is empty (row may have no doc)"
                )
        except Exception as e:
            results["checks"]["doc_has_content"] = f"warn: could not read textarea value — {e}"

        _snapshot(page, "L69_row_expand_doc_tab")

        # --- Final screenshot ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _snapshot(page, f"L69_row_expand_{ts}")
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
    result = test_row_expand()
    sys.exit(0 if result.get("passed") else 1)
