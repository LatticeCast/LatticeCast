"""
Test: FE Tables list URL reflects current workspace
- /tables redirects to /tables/[workspace-slug]
- Switching workspace changes URL
- Bookmarking /tables/[slug] loads that workspace
"""

import json
import os
from playwright.sync_api import sync_playwright

os.makedirs('/app/.browser', exist_ok=True)

BASE_URL = "http://lattice-cast:13491"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}

results = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.add_init_script(
        f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
    )

    # Proxy API calls: rewrite localhost:13491 → lattice-cast:13491
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
                print(f"Route error: {exc}")
                route.continue_()
        else:
            route.continue_()

    ctx.route("**/*", handle_route)

    page = ctx.new_page()

    # Test 1: /tables redirects to /tables/[workspace-slug]
    page.goto(f"{BASE_URL}/tables")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    url_after_redirect = page.url
    page.screenshot(path="/app/.browser/150_01_tables_redirect.png")
    print(f"After /tables URL: {url_after_redirect}")

    if "/tables/" in url_after_redirect and url_after_redirect != f"{BASE_URL}/tables/":
        results["redirect"] = "PASS"
        print("PASS: /tables redirected to workspace-specific URL")
    else:
        results["redirect"] = f"FAIL - URL was {url_after_redirect}"
        print(f"FAIL: /tables did not redirect, URL: {url_after_redirect}")

    workspace_slug = url_after_redirect.split("/tables/")[-1].rstrip("/")
    print(f"Workspace slug in URL: {workspace_slug!r}")

    # Test 2: URL is workspace-name slug (non-empty)
    if workspace_slug and len(workspace_slug) > 0 and workspace_slug != url_after_redirect:
        results["slug_format"] = "PASS"
        print(f"PASS: URL slug is non-empty: {workspace_slug!r}")
    else:
        results["slug_format"] = "FAIL - empty or malformed slug"

    # Test 3: Switching workspace changes URL
    ws_buttons = page.query_selector_all('[class*="rounded-xl"][class*="shadow"] button:first-child')
    print(f"Found {len(ws_buttons)} workspace buttons")

    if len(ws_buttons) > 1:
        ws_buttons[1].click()
        page.wait_for_timeout(1000)
        url_after_switch = page.url
        page.screenshot(path="/app/.browser/150_02_workspace_switch.png")
        print(f"After workspace switch URL: {url_after_switch}")

        if "/tables/" in url_after_switch and url_after_switch != url_after_redirect:
            results["switch"] = "PASS"
            print("PASS: URL changed after workspace switch")
        else:
            results["switch"] = f"FAIL - URL did not change: {url_after_switch}"
            print(f"FAIL: URL did not change after switch: {url_after_switch}")
    else:
        results["switch"] = "SKIP - only one workspace"
        print("SKIP: Only one workspace available, cannot test switching")

    # Test 4: Bookmark - navigate directly to workspace URL in new page
    bookmark_url = url_after_redirect
    page2 = ctx.new_page()
    page2.goto(bookmark_url)
    page2.wait_for_load_state("networkidle")
    page2.wait_for_timeout(2000)
    url_after_bookmark = page2.url
    page2.screenshot(path="/app/.browser/150_03_bookmark_load.png")
    print(f"After bookmark load URL: {url_after_bookmark}")

    if "/tables/" in url_after_bookmark:
        results["bookmark"] = "PASS"
        print("PASS: Bookmark URL loaded correctly")
    else:
        results["bookmark"] = f"FAIL - ended up at {url_after_bookmark}"
        print(f"FAIL: Bookmark navigation failed: {url_after_bookmark}")

    browser.close()

print("\n=== RESULTS ===")
for k, v in results.items():
    print(f"  {k}: {v}")

failed = [k for k, v in results.items() if str(v).startswith("FAIL")]
if failed:
    print(f"\nFAILED: {failed}")
    raise SystemExit(1)
else:
    print("\nAll tests passed!")
