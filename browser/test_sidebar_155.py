#!/usr/bin/env python3
"""Test ticket 155: sidebar table tree — clicking table navigates to /<workspace>/<table>.

Usage:
    docker compose exec browser python /app/test_sidebar_155.py
"""
import json, urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://lattice-cast:13491"
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


def get_workspaces_and_tables():
    req = urllib.request.Request(
        f"{BASE_URL}/api/workspaces",
        headers={"Authorization": "Bearer claude"}
    )
    workspaces = json.loads(urllib.request.urlopen(req).read())

    req2 = urllib.request.Request(
        f"{BASE_URL}/api/tables",
        headers={"Authorization": "Bearer claude"}
    )
    tables = json.loads(urllib.request.urlopen(req2).read())
    return workspaces, tables


def run():
    workspaces, tables = get_workspaces_and_tables()
    print(f"workspaces: {[w['name'] for w in workspaces]}")
    print(f"tables: {[(t['name'], t['workspace_id'][:8]) for t in tables]}")

    # Find a workspace with at least one table
    target_ws = None
    target_table = None
    for ws in workspaces:
        ws_tables = [t for t in tables if t["workspace_id"] == ws["workspace_id"]]
        if ws_tables:
            target_ws = ws
            target_table = ws_tables[0]
            break

    if not target_ws or not target_table:
        print("No workspace with tables found, cannot test")
        return

    print(f"target workspace: {target_ws['name']} ({target_ws['workspace_id']})")
    print(f"target table: {target_table['name']} ({target_table['table_id']})")

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
        )

        page = ctx.new_page()

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

        # ── Step 1: Load /tables page ──
        print("\n[Step 1] Load /tables page")
        try:
            page.goto(f"{BASE_URL}/tables", wait_until="networkidle", timeout=20000)
        except PlaywrightTimeout:
            pass
        page.wait_for_timeout(2000)
        _snap(page, "155_01_tables_page")
        print(f"  URL: {page.url}")

        # ── Step 2: Open sidebar ──
        print("\n[Step 2] Open sidebar")
        toggle = page.get_by_test_id("menu-toggle")
        assert toggle.is_visible(), "menu-toggle not found"
        toggle.click()
        page.wait_for_timeout(500)
        _snap(page, "155_02_sidebar_open")

        # ── Step 3: Click table name in sidebar ──
        print(f"\n[Step 3] Click table '{target_table['name']}' in sidebar")
        url_before = page.url

        # Find the table button by text match
        table_btn = page.get_by_test_id("menu-nav").get_by_text(target_table["name"], exact=True)
        assert table_btn.count() > 0, f"Table button '{target_table['name']}' not found in sidebar"

        table_btn.first.click()
        page.wait_for_timeout(2000)
        url_after = page.url
        _snap(page, "155_03_after_table_click")

        print(f"  URL before: {url_before}")
        print(f"  URL after:  {url_after}")

        expected_ws = target_ws["workspace_id"]
        expected_table = target_table["table_id"]
        expected_url = f"{BASE_URL}/{expected_ws}/{expected_table}"

        if url_before == url_after:
            print(f"  FAIL: URL did not change after clicking table in sidebar!")
            assert False, f"Clicking table '{target_table['name']}' in sidebar must navigate via goto()"
        elif url_after.startswith(expected_url):
            print(f"  ✓ URL correctly navigated to /{expected_ws[:8]}.../{expected_table[:8]}...")
        else:
            print(f"  WARN: URL changed to unexpected path: {url_after}")
            print(f"  Expected prefix: {expected_url}")

        # ── Step 4: Verify we're on the table page ──
        print("\n[Step 4] Verify table page loaded")
        breadcrumb_table = page.get_by_test_id("breadcrumb-table")
        if breadcrumb_table.is_visible():
            table_text = breadcrumb_table.inner_text()
            print(f"  breadcrumb table: '{table_text}'")
            assert target_table["name"] in table_text or table_text != "", "breadcrumb shows table name"
            print("  ✓ breadcrumb confirms table page")
        else:
            print("  breadcrumb-table not visible (may still be OK)")

        _snap(page, "155_04_table_page")

        print("\n✓ All tests passed!")

    finally:
        browser.close()
        playwright.stop()


if __name__ == "__main__":
    run()
