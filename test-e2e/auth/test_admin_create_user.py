"""
E2E test: task-12 — Admin creates user + default workspace cascade.

Flow:
  1. (API) Login as admin 'lattice'
  2. (API) Create new test user via POST /api/v1/admin/users
  3. (API) Verify user exists — GET /api/v1/admin/users/{email}
  4. (API) New user logs in; GET /workspaces → 1 workspace, workspace_name = email
  5. (API) GET /workspaces/{ws_id}/members → new user has role='owner'
  6. (UI)  New user opens workspace page → workspace-tab-strip is visible
  7. (API) Teardown: DELETE test user
"""

import json
import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, login

SUFFIX = str(int(time.time()) % 100000)
TEST_EMAIL = f"e2e-admin-{SUFFIX}@e2e.local"
SCREENSHOT_DIR = "/output"
ADMIN_USER = "lattice"


def snap(page, name: str) -> None:
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_admin_create_user(browser, admin_token, snapshot):
    """Admin creates user + default ws cascade (row_id=79 parent=70)."""
    print(f"[0] Setup — test email: {TEST_EMAIL}")

    # Step 1: Admin login (using conftest fixture)
    print("[1] Admin login")

    # Idempotent cleanup — delete leftover from a previous run
    api("DELETE", f"/api/v1/admin/users/{TEST_EMAIL}", admin_token)

    # Step 2: Admin creates user
    print("[2] Admin creates user")
    r = api("POST", "/api/v1/admin/users", admin_token, json={"email": TEST_EMAIL, "role": "user"})
    assert r.status_code == 201, f"create user: {r.status_code} {r.text[:300]}"
    created = r.json()
    user_id = created["user_id"]
    user_name = created["user_name"]
    print(f"    user_id={user_id} user_name={user_name}")

    # Step 3: API verify — user retrievable via admin endpoint
    print("[3] API verify: user exists in admin endpoint")
    r = api("GET", f"/api/v1/admin/users/{TEST_EMAIL}", admin_token)
    assert r.status_code == 200, f"get user: {r.status_code} {r.text[:200]}"
    fetched = r.json()
    assert fetched["email"] == TEST_EMAIL, f"email mismatch: {fetched['email']!r}"
    assert fetched["role"] == "user", f"role mismatch: {fetched['role']!r}"
    assert fetched["user_id"] == user_id, f"user_id mismatch: {fetched['user_id']!r}"
    print("    PASS: correct email, role, user_id")

    # Step 4: New user login + workspace cascade
    print("[4] API verify: default workspace cascaded")
    new_token = login(TEST_EMAIL)
    r = api("GET", "/api/v1/workspaces", new_token)
    assert r.status_code == 200, f"list workspaces: {r.status_code} {r.text[:200]}"
    workspaces = r.json()
    assert len(workspaces) == 1, f"expected 1 workspace, got {len(workspaces)}: {json.dumps(workspaces)}"
    ws = workspaces[0]
    assert ws["workspace_name"] == TEST_EMAIL, (
        f"workspace_name mismatch: got {ws['workspace_name']!r}, want {TEST_EMAIL!r}"
    )
    ws_id = ws["workspace_id"]
    print(f"    PASS: workspace_name={ws['workspace_name']} ws_id={ws_id}")

    # Step 5: API verify — new user is owner of their default workspace
    print("[5] API verify: new user is workspace owner")
    r = api("GET", f"/api/v1/workspaces/{ws_id}/members", new_token)
    assert r.status_code == 200, f"list members: {r.status_code} {r.text[:200]}"
    members = r.json()
    owner_entries = [m for m in members if m["role"] == "owner" and m["email"] == TEST_EMAIL]
    assert owner_entries, f"new user not found as owner in: {json.dumps(members)}"
    print("    PASS: user has owner role")

    # Step 6: UI verify — new user can see their workspace page
    print("[6] UI: new user opens workspace page")
    login_info = {
        "provider": "none",
        "accessToken": new_token,
        "userInfo": {"sub": new_token, "email": TEST_EMAIL, "name": user_name},
        "role": "user",
    }

    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    ctx.add_init_script(
        f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(login_info)}));"
    )
    page = ctx.new_page()

    try:
        # Navigate by UUID — avoids URL-encoding issues with @ in the email workspace_name
        page.goto(f"{BASE}/{ws_id}/", wait_until="networkidle", timeout=20000)

        if "/login" in page.url:
            if snapshot:
                snap(page, "admin_create_FAIL_redirected_login")
            pytest.fail("redirected to /login — auth seed did not take effect")

        if snapshot:
            snap(page, "admin_create_01_workspace_page")

        try:
            page.wait_for_selector("[data-testid='workspace-tab-strip']", timeout=15000)
        except PlaywrightTimeout:
            if snapshot:
                snap(page, "admin_create_FAIL_no_tabstrip")
            pytest.fail("workspace-tab-strip not visible — workspace page failed to render")

        ws_tab = page.locator(f"[data-testid='workspace-tab-{ws_id}']")
        if ws_tab.count() == 0:
            if snapshot:
                snap(page, "admin_create_FAIL_no_ws_tab")
            pytest.fail(f"workspace-tab-{ws_id} absent — workspace not in tab strip")

        print("    PASS: workspace-tab-strip visible and workspace tab present")

        if snapshot:
            snap(page, "admin_create_02_tabstrip_ok")

    finally:
        ctx.close()

    # Step 7: Teardown
    print("[7] Teardown: delete test user")
    r = api("DELETE", f"/api/v1/admin/users/{TEST_EMAIL}", admin_token)
    if r.status_code not in (204, 404):
        print(f"    WARN: delete returned {r.status_code} {r.text[:100]}")
    else:
        print("    deleted")

    print("\nPASS")
