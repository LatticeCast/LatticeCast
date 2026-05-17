#!/usr/bin/env python3
"""
E2E test: task-50 — remove member loses access

Verifies:
  1. Setup: create workspace + second user; add as member via API.
  2. UI: owner navigates to members page; member row visible.
  3. UI: owner clicks remove button → member row disappears.
  4. BE: GET /workspaces/{ws_id}/members no longer includes removed user.
  5. BE: removed user cannot access the workspace (403).
  6. UI: removed user navigates to workspace → denied / redirected.
  7. Teardown: delete workspace + test user.

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_workspace_member_remove.py [--snapshot]
"""

import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
SCREENSHOT_DIR = "/output"

ADMIN_USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-remove-{SUFFIX}"
MEMBER_USER = f"e2e-remove-{SUFFIX}"
MEMBER_EMAIL = f"{MEMBER_USER}@e2e.local"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def run() -> None:
    # ── Auth ─────────────────────────────────────────────────────────────────
    print("[0] Login as admin")
    admin_token = login(ADMIN_USER)

    # ── Setup: create workspace ──────────────────────────────────────────────
    print(f"[1] Setup: create workspace '{WS_NAME}'")
    r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]

    # ── Setup: create member user ────────────────────────────────────────────
    print(f"[2] Setup: create member user '{MEMBER_EMAIL}'")
    api("DELETE", f"/api/v1/admin/users/{MEMBER_EMAIL}", admin_token)
    r = api("POST", "/api/v1/admin/users", admin_token, json={"email": MEMBER_EMAIL, "role": "user"})
    if r.status_code != 201:
        fatal(f"create member user: {r.status_code} {r.text[:200]}")
    member_user_id = r.json()["user_id"]
    member_user_name = r.json().get("user_name", MEMBER_USER)
    print(f"    member user_id={member_user_id}")

    # ── Setup: add member to workspace ───────────────────────────────────────
    print("[3] Setup: add member to workspace via API")
    r = api("POST", f"/api/v1/workspaces/{ws_id}/members", admin_token,
            json={"user_email": MEMBER_EMAIL, "role": "member"})
    if r.status_code != 201:
        fatal(f"add member: {r.status_code} {r.text[:200]}")

    # ── Playwright (owner session) ───────────────────────────────────────────
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, admin_token, ADMIN_USER, role="admin")

        # ── Step 4: Navigate to members page, verify member present ──────────
        print(f"[4] UI: navigate to /{WS_NAME}/members")
        page.goto(f"{BASE}/{WS_NAME}/members", wait_until="networkidle")
        if "/login" in page.url:
            fatal("Redirected to /login — auth failed")

        heading = page.get_by_test_id("members-heading")
        heading.wait_for(state="visible", timeout=10000)

        member_row = page.get_by_test_id(f"member-row-{member_user_id}")
        member_row.wait_for(state="visible", timeout=5000)
        snap(page, "t50_01_member_present")
        print(f"    member row visible: member-row-{member_user_id}")

        # ── Step 5: Click remove button → member row disappears ──────────────
        print("[5] UI: click remove button")
        remove_btn = page.get_by_test_id(f"remove-btn-{member_user_id}")
        remove_btn.wait_for(state="visible", timeout=5000)

        with page.expect_response("**/api/v1/workspaces/*/members/*") as resp_info:
            remove_btn.click()
        resp = resp_info.value
        assert resp.status == 204, f"DELETE member API returned {resp.status}"

        member_row.wait_for(state="hidden", timeout=5000)
        snap(page, "t50_02_member_removed")
        print("    member row hidden after removal")

        # ── Step 6: BE verify — member NOT in list anymore ───────────────────
        print("[6] BE verify: member not in workspace members list")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200, f"list members: {r.status_code}"
        members = r.json()
        removed = next((m for m in members if m["user_id"] == member_user_id), None)
        assert removed is None, f"Member still in list after removal: {removed}"
        print("    BE: member not in members list")

        # ── Step 7: BE verify — removed user cannot access workspace ─────────
        print("[7] BE verify: removed user cannot access workspace")
        member_token = login(member_user_name)
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", member_token)
        assert r.status_code in (403, 404), (
            f"Removed user should get 403/404, got {r.status_code}"
        )
        print(f"    removed user gets {r.status_code} — access denied")

        # ── Step 8: UI verify — removed user sees no access ──────────────────
        print("[8] UI: removed user navigates to workspace → denied")
        page2 = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page2, member_token, member_user_name, role="user")
        page2.goto(f"{BASE}/{WS_NAME}/members", wait_until="commit")
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_url(lambda url: "/members" not in url, timeout=10000)
        snap(page2, "t50_03_member_denied")

        denied = "/members" not in page2.url
        assert denied, f"Removed user should not see members page; url={page2.url}"
        print(f"    removed user denied access (url={page2.url})")

        page2.close()
        browser.close()

    # ── Teardown ─────────────────────────────────────────────────────────────
    print("[9] Teardown: delete workspace + member user")
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)
    assert r.status_code == 204, f"Delete workspace failed: {r.status_code}"
    r = api("DELETE", f"/api/v1/admin/users/{MEMBER_EMAIL}", admin_token)
    if r.status_code not in (204, 404):
        print(f"    WARN: delete user returned {r.status_code}")

    print("PASS: e2e_test_workspace_member_remove")


if __name__ == "__main__":
    run()
