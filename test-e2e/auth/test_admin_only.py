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
"""

import json
import time

import pytest

from e2e_base import BASE, api, login

ADMIN_USER = "lattice"
ADMIN_PATH = "/api/v1/admin/users"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def assert_403(resp, label: str) -> None:
    assert resp.status_code == 403, (
        f"{label}: expected 403, got {resp.status_code} — {resp.text[:200]}"
    )
    body = resp.json()
    assert "Admin access required" in body.get("detail", ""), (
        f"{label}: 403 but wrong detail — {body}"
    )
    print(f"    PASS: {label} → 403")


@pytest.fixture()
def test_user(admin_token):
    suffix = str(int(time.time()) % 100000)
    test_email = f"e2e-adminonly-{suffix}@e2e.local"

    # Idempotent cleanup
    api("DELETE", f"{ADMIN_PATH}/{test_email}", admin_token)

    print(f"[0] Setup — test email: {test_email}")
    print("[2] Create non-admin test user")
    r = api("POST", ADMIN_PATH, admin_token, json={"email": test_email, "role": "user"})
    assert r.status_code == 201, f"create user: {r.status_code} {r.text[:300]}"
    user_name = r.json()["user_name"]
    print(f"    created: {user_name}")

    user_token = login(test_email)

    yield test_email, user_name, user_token

    # Step 10: Teardown
    print("[10] Teardown: delete test user")
    r = api("DELETE", f"{ADMIN_PATH}/{test_email}", admin_token)
    if r.status_code not in (204, 404):
        print(f"    WARN: delete returned {r.status_code}")
    else:
        print("    deleted")


def test_admin_only(browser, admin_token, test_user, request):
    snapshot = request.config.getoption("--snapshot", default=False)
    test_email, user_name, user_token = test_user

    # Step 1: Admin login
    print("[1] Admin login")

    # Step 3: Positive control — admin CAN access
    print("[3] Positive control: admin GET /admin/users → 200")
    r = api("GET", ADMIN_PATH, admin_token)
    assert r.status_code == 200, f"admin GET failed: {r.status_code} {r.text[:200]}"
    print("    PASS: admin GET → 200")

    # Step 4: Non-admin login + GET /admin/users → 403
    print("[4] Non-admin: GET /admin/users → 403")
    r = api("GET", ADMIN_PATH, user_token)
    assert_403(r, "GET /admin/users")

    # Step 5: Non-admin POST /admin/users → 403
    print("[5] Non-admin: POST /admin/users → 403")
    r = api("POST", ADMIN_PATH, user_token, json={"email": "should-not-exist@e2e.local", "role": "user"})
    assert_403(r, "POST /admin/users")

    # Step 6: Non-admin GET /admin/users/{email} → 403
    print("[6] Non-admin: GET /admin/users/{email} → 403")
    r = api("GET", f"{ADMIN_PATH}/{test_email}", user_token)
    assert_403(r, "GET /admin/users/{email}")

    # Step 7: Non-admin PUT /admin/users/{email} → 403
    print("[7] Non-admin: PUT /admin/users/{email} → 403")
    r = api("PUT", f"{ADMIN_PATH}/{test_email}", user_token, json={"role": "admin"})
    assert_403(r, "PUT /admin/users/{email}")

    # Step 8: Non-admin DELETE /admin/users/{email} → 403
    print("[8] Non-admin: DELETE /admin/users/{email} → 403")
    r = api("DELETE", f"{ADMIN_PATH}/{test_email}", user_token)
    assert_403(r, "DELETE /admin/users/{email}")

    # Step 9: UI pillar — browser-side fetch as non-admin → 403
    print("[9] UI: browser fetch /admin/users as non-admin → 403")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    login_info = json.dumps({
        "provider": "none",
        "accessToken": user_token,
        "userInfo": {"sub": user_token, "email": test_email, "name": user_name},
        "role": "user",
    })
    ctx.add_init_script(
        f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(login_info)}));"
    )
    page = ctx.new_page()
    try:
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
        snap(page, "auth_admin_only_01_home", snapshot)

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
            snap(page, "auth_admin_only_FAIL_browser_fetch", snapshot)
        assert status == 403, f"browser fetch: expected 403, got {status}"
        print("    PASS: browser fetch → 403")
        snap(page, "auth_admin_only_02_done", snapshot)
    finally:
        page.close()
        ctx.close()

    print("\nPASS")
