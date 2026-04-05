#!/usr/bin/env python3
"""Test ticket 154: breadcrumb mirrors URL — workspace/table/row segments.

Usage:
    docker compose exec browser python /app/test_154_breadcrumb_url.py
"""
import json, urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://lattice-cast:13491"
TABLE_ID = "7e6821be-3de8-4e54-b0b6-05db91e5f797"
SCREENSHOT_DIR = "/output"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}


def _snap(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=False)
        print(f"  screenshot: {path}")
    except Exception as e:
        print(f"  screenshot failed: {e}")
    return path


def get_workspace_id():
    req = urllib.request.Request(
        f"{BASE_URL}/api/tables/{TABLE_ID}",
        headers={"Authorization": "Bearer claude"}
    )
    data = json.loads(urllib.request.urlopen(req).read())
    return data["workspace_id"]


def run():
    ws_id = get_workspace_id()
    print(f"workspace_id: {ws_id}")

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

        # Rewrite localhost:13491 → lattice-cast:13491 for API calls
        def handle_route(route):
            url = route.request.url
            if "localhost:13491/api" in url:
                new_url = url.replace("localhost:13491", "lattice-cast:13491")
                try:
                    resp = ctx.request.fetch(
                        new_url,
                        method=route.request.method,
                        headers={"Authorization": "Bearer claude", "Content-Type": "application/json"},
                    )
                    route.fulfill(response=resp)
                except Exception as exc:
                    print(f"  route error: {exc}")
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        # ── Step 1: Table page — breadcrumb shows workspace / table, NOT row ──
        print("\n[Step 1] Table page")
        try:
            page.goto(f"{BASE_URL}/{ws_id}/{TABLE_ID}", wait_until="networkidle", timeout=20000)
        except PlaywrightTimeout:
            pass
        page.wait_for_timeout(3000)
        _snap(page, "154_01_table_breadcrumb")
        print(f"  URL: {page.url}")

        ws_btn = page.get_by_test_id("breadcrumb-workspace")
        tbl_btn = page.get_by_test_id("breadcrumb-table")
        row_btn = page.get_by_test_id("breadcrumb-row")

        assert ws_btn.is_visible(), "workspace segment must be visible on table page"
        assert tbl_btn.is_visible(), "table segment must be visible on table page"
        assert row_btn.count() == 0, f"row segment must NOT appear on table page, count={row_btn.count()}"

        ws_text = ws_btn.inner_text()
        tbl_text = tbl_btn.inner_text()
        print(f"  workspace='{ws_text}' table='{tbl_text}'")
        assert ws_text != ws_id, f"workspace should show name not UUID, got: {ws_text}"

        print("  ✓ table page breadcrumb OK")

        # ── Step 2: Row page — breadcrumb shows workspace / table / row_number ──
        print("\n[Step 2] Row page (row 154)")
        try:
            page.goto(f"{BASE_URL}/{ws_id}/{TABLE_ID}/154", wait_until="networkidle", timeout=20000)
        except PlaywrightTimeout:
            pass
        page.wait_for_timeout(3000)
        _snap(page, "154_02_row_breadcrumb")
        print(f"  URL: {page.url}")

        ws_btn2 = page.get_by_test_id("breadcrumb-workspace")
        tbl_btn2 = page.get_by_test_id("breadcrumb-table")
        row_btn2 = page.get_by_test_id("breadcrumb-row")

        assert ws_btn2.is_visible(), "workspace segment must be visible on row page"
        assert tbl_btn2.is_visible(), "table segment must be visible on row page"
        assert row_btn2.is_visible(), "row segment must be visible on row page"

        row_text = row_btn2.inner_text()
        print(f"  workspace='{ws_btn2.inner_text()}' table='{tbl_btn2.inner_text()}' row='{row_text}'")
        assert "154" in row_text, f"row segment must contain '154', got: {row_text}"

        print("  ✓ row page breadcrumb OK")

        # ── Step 3: Click table segment → navigate to table page ──
        print("\n[Step 3] Click table segment")
        tbl_btn2.click()
        page.wait_for_timeout(2000)
        _snap(page, "154_03_after_table_click")
        print(f"  URL after click: {page.url}")
        expected = f"{BASE_URL}/{ws_id}/{TABLE_ID}"
        assert page.url.startswith(expected), f"Expected table URL {expected}, got: {page.url}"
        print("  ✓ table segment click navigates to table page")

        # ── Step 4: From row page, click workspace segment → navigate to /tables ──
        print("\n[Step 4] Click workspace segment")
        try:
            page.goto(f"{BASE_URL}/{ws_id}/{TABLE_ID}/154", wait_until="networkidle", timeout=20000)
        except PlaywrightTimeout:
            pass
        page.wait_for_timeout(2000)
        page.get_by_test_id("breadcrumb-workspace").click()
        page.wait_for_timeout(2000)
        _snap(page, "154_04_after_workspace_click")
        print(f"  URL after click: {page.url}")
        assert "/tables" in page.url, f"Expected /tables in URL, got: {page.url}"
        print("  ✓ workspace segment click navigates to /tables")

        print("\n✓ All tests passed!")
    finally:
        browser.close()
        playwright.stop()


if __name__ == "__main__":
    run()
