#!/usr/bin/env python3
"""task-54: e2e_test_auth_admin_only — non-admin 403 on /admin/users.

Verifies:
 - Admin user (lattice) can access all /api/v1/admin/users endpoints (200/201)
 - Non-admin user gets 403 on every /api/v1/admin/users operation
 - 403 response body contains "Admin access required"

Flow:
  1. (API) Login as admin 'lattice'
  2. (API) Create a temporary non-admin test user
  3. (API) Positive control: admin can GET /admin/users (200)
  4. (API) Non-admin login → GET /admin/users → 403
  5. (API) Non-admin → POST /admin/users → 403
  6. (API) Non-admin → GET /admin/users/{email} → 403
  7. (API) Non-admin → PUT /admin/users/{email} → 403
  8. (API) Non-admin → DELETE /admin/users/{email} → 403
  9. (UI)  Non-admin fetches /api/v1/admin/users via page.evaluate → 403
 10. (API) Teardown: delete test user

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_auth_admin_only.py [--snapshot]
"""

import json
import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, api, connect_browser, fatal, login

SNAPSHOT = "--snapshot" in sys.argv
SUFFIX = str(int(time.time()) % 100000)
TEST_EMAIL = f"e2e-adminonly-{SUFFIX}@e2e.local"
ADMIN_USER = "lattice"
ADMIN_PATH = "/api/v1/admin/users"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def assert_403(resp, label: str) -> None:
    if resp.status_code != 403:
        fatal(f"{label}: expected 403, got {resp.status_code} — {resp.text[:200]}")
    body = resp.json()
    if "Admin access required" not in body.get("detail", ""):
        fatal(f"{label}: 403 but wrong detail — {body}")
    print(f"    PASS: {label} → 403")


def run() -> None:
    print(f"[0] Setup — test email: {TEST_EMAIL}")

    # Step 1: Admin login
    print("[1] Admin login")
    admin_token = login(ADMIN_USER)

    # Idempotent cleanup
    api("DELETE", f"{ADMIN_PATH}/{TEST_EMAIL}", admin_token)

    # Step 2: Create non-admin test user
    print("[2] Create non-admin test user")
    r = api("POST", ADMIN_PATH, admin_token, json={"email": TEST_EMAIL, "role": "user"})
    if r.status_code != 201:
        fatal(f"create user: {r.status_code} {r.text[:300]}")
    user_name = r.json()["user_name"]
    print(f"    created: {user_name}")

    # Step 3: Positive control — admin CAN access
    print("[3] Positive control: admin GET /admin/users → 200")
    r = api("GET", ADMIN_PATH, admin_token)
    if r.status_code != 200:
        fatal(f"admin GET failed: {r.status_code} {r.text[:200]}")
    print("    PASS: admin GET → 200")

    # Step 4: Non-admin login + GET /admin/users → 403
    print("[4] Non-admin: GET /admin/users → 403")
    user_token = login(TEST_EMAIL)
    r = api("GET", ADMIN_PATH, user_token)
    assert_403(r, "GET /admin/users")

    # Step 5: Non-admin POST /admin/users → 403
    print("[5] Non-admin: POST /admin/users → 403")
    r = api("POST", ADMIN_PATH, user_token, json={"email": "should-not-exist@e2e.local", "role": "user"})
    assert_403(r, "POST /admin/users")

    # Step 6: Non-admin GET /admin/users/{email} → 403
    print("[6] Non-admin: GET /admin/users/{email} → 403")
    r = api("GET", f"{ADMIN_PATH}/{TEST_EMAIL}", user_token)
    assert_403(r, "GET /admin/users/{email}")

    # Step 7: Non-admin PUT /admin/users/{email} → 403
    print("[7] Non-admin: PUT /admin/users/{email} → 403")
    r = api("PUT", f"{ADMIN_PATH}/{TEST_EMAIL}", user_token, json={"role": "admin"})
    assert_403(r, "PUT /admin/users/{email}")

    # Step 8: Non-admin DELETE /admin/users/{email} → 403
    print("[8] Non-admin: DELETE /admin/users/{email} → 403")
    r = api("DELETE", f"{ADMIN_PATH}/{TEST_EMAIL}", user_token)
    assert_403(r, "DELETE /admin/users/{email}")

    # Step 9: UI pillar — browser-side fetch as non-admin → 403
    print("[9] UI: browser fetch /admin/users as non-admin → 403")
    pw = sync_playwright().start()
    browser = connect_browser(pw)
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        login_info = json.dumps({
            "provider": "none",
            "accessToken": user_token,
            "userInfo": {"sub": user_token, "email": TEST_EMAIL, "name": user_name},
            "role": "user",
        })
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(login_info)}));"
        )
        page = ctx.new_page()
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
        snap(page, "auth_admin_only_01_home")

        status = page.evaluate(
            """async () => {
                const info = JSON.parse(localStorage.getItem('loginInfo'));
                const resp = await fetch('/api/v1/admin/users', {
                    headers: { 'Authorization': 'Bearer ' + info.accessToken }
                });
                return resp.status;
            }"""
        )
        if status != 403:
            snap(page, "auth_admin_only_FAIL_browser_fetch")
            fatal(f"browser fetch: expected 403, got {status}")
        print("    PASS: browser fetch → 403")
        snap(page, "auth_admin_only_02_done")
    finally:
        browser.close()
        pw.stop()

    # Step 10: Teardown
    print("[10] Teardown: delete test user")
    r = api("DELETE", f"{ADMIN_PATH}/{TEST_EMAIL}", admin_token)
    if r.status_code not in (204, 404):
        print(f"    WARN: delete returned {r.status_code}")
    else:
        print("    deleted")

    print("\nPASS")


if __name__ == "__main__":
    run()
