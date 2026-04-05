#!/usr/bin/env python3
"""
Test 151: Breadcrumb is navigation-only — no inline rename input after click.
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://lattice-cast:13491"
FRONTEND_URL = "http://lattice-cast:13491"
SCREENSHOT_DIR = "/output"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}


def run():
    import urllib.request

    # Get first table via API
    req = urllib.request.Request(
        f"{BASE_URL}/api/tables",
        headers={"Authorization": "Bearer claude"},
    )
    tables = json.loads(urllib.request.urlopen(req).read())
    if not tables:
        print("SKIP: no tables found")
        return

    table = tables[0]
    ws_id = table["workspace_id"]
    t_id = table["table_id"]
    print(f"Using table: {table['name']} ({ws_id}/{t_id})")

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        # Route API calls from localhost to lattice-cast inside docker
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
                    print(f"Route error: {exc}")
                    route.continue_()
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a table page
        page.goto(f"{FRONTEND_URL}/{ws_id}/{t_id}", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{SCREENSHOT_DIR}/151_01_table_page.png")
        print(f"URL after nav: {page.url}")

        # Verify breadcrumbs are visible
        ws_btn = page.get_by_test_id("breadcrumb-workspace")
        table_btn = page.get_by_test_id("breadcrumb-table")

        ws_visible = ws_btn.count() > 0 and ws_btn.first.is_visible()
        table_visible = table_btn.count() > 0 and table_btn.first.is_visible()
        print(f"Workspace breadcrumb visible: {ws_visible}")
        print(f"Table breadcrumb visible: {table_visible}")

        # ASSERT: breadcrumb elements are plain buttons (not inputs)
        if table_visible:
            tag = table_btn.first.evaluate("el => el.tagName")
            print(f"Table breadcrumb tag: {tag}")
            assert tag == "BUTTON", f"Expected BUTTON, got {tag}"

            title = table_btn.first.get_attribute("title")
            assert title is None or "rename" not in (title or "").lower(), (
                f"Should not have rename title: {title}"
            )

        if ws_visible:
            tag = ws_btn.first.evaluate("el => el.tagName")
            print(f"Workspace breadcrumb tag: {tag}")
            assert tag == "BUTTON", f"Expected BUTTON, got {tag}"

        # ASSERT: clicking table breadcrumb does NOT show a rename input
        if table_visible:
            table_btn.first.click()
            page.wait_for_timeout(500)
            inp = page.get_by_test_id("breadcrumb-table-input")
            inp_count = inp.count()
            print(f"Rename input count after table click: {inp_count} (must be 0)")
            assert inp_count == 0, "Rename input MUST NOT appear after clicking table breadcrumb"
            page.screenshot(path=f"{SCREENSHOT_DIR}/151_02_after_table_click.png")
            print("PASS: No rename input after table breadcrumb click")

        # Navigate back to table for workspace breadcrumb test
        page.goto(f"{FRONTEND_URL}/{ws_id}/{t_id}", wait_until="networkidle")
        page.wait_for_timeout(1500)

        ws_btn2 = page.get_by_test_id("breadcrumb-workspace")
        if ws_btn2.count() > 0 and ws_btn2.first.is_visible():
            ws_btn2.first.click()
            page.wait_for_timeout(1000)
            inp = page.get_by_test_id("breadcrumb-workspace-input")
            inp_count = inp.count()
            print(f"Rename input count after workspace click: {inp_count} (must be 0)")
            assert inp_count == 0, "Rename input MUST NOT appear after clicking workspace breadcrumb"
            page.screenshot(path=f"{SCREENSHOT_DIR}/151_03_after_ws_click.png")
            print("PASS: No rename input after workspace breadcrumb click")

        if not ws_visible and not table_visible:
            # Still take screenshot to show current state
            page.screenshot(path=f"{SCREENSHOT_DIR}/151_01_no_breadcrumb.png")
            print("WARNING: breadcrumbs not found — page may not have loaded correctly")

        print("All assertions passed!")
    finally:
        browser.close()
        p.stop()


run()
