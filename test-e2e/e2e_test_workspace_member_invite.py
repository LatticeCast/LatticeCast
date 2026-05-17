#!/usr/bin/env python3
"""
E2E test: task-48 — add member by user_name/email

Verifies:
  1. Setup: create workspace + second test user via API.
  2. UI: navigate to members page; "Add Member" panel visible for owner.
  3. UI: type invitee email → click Add → new member appears in list.
  4. BE: GET /workspaces/{ws_id}/members includes the new member.
  5. UI: invite non-existent email → error message displayed.
  6. UI: invite already-added email → error message (conflict).
  7. Teardown: DELETE workspace + test user.

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_workspace_member_invite.py [--snapshot]
"""

import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
SCREENSHOT_DIR = "/output"

ADMIN_USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-invite-{SUFFIX}"
INVITEE_EMAIL = f"e2e-invite-{SUFFIX}@e2e.local"


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

    # ── Setup: create invitee user ───────────────────────────────────────────
    print(f"[2] Setup: create invitee user '{INVITEE_EMAIL}'")
    api("DELETE", f"/api/v1/admin/users/{INVITEE_EMAIL}", admin_token)
    r = api("POST", "/api/v1/admin/users", admin_token, json={"email": INVITEE_EMAIL, "role": "user"})
    if r.status_code != 201:
        fatal(f"create invitee: {r.status_code} {r.text[:200]}")
    invitee_user_id = r.json()["user_id"]
    print(f"    invitee user_id={invitee_user_id}")

    # ── Playwright ───────────────────────────────────────────────────────────
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, admin_token, ADMIN_USER, role="admin")

        # ── Step 3: Navigate to members page ─────────────────────────────────
        print(f"[3] UI: navigate to /{WS_NAME}/members")
        page.goto(f"{BASE}/{WS_NAME}/members", wait_until="networkidle")
        if "/login" in page.url:
            fatal("Redirected to /login — auth failed")

        heading = page.get_by_test_id("members-heading")
        heading.wait_for(state="visible", timeout=10000)
        snap(page, "t48_01_members_page")

        # ── Step 4: Verify Add Member panel visible (owner) ──────────────────
        print("[4] UI: verify Add Member panel visible")
        email_input = page.get_by_test_id("member-email-input")
        email_input.wait_for(state="visible", timeout=5000)
        add_btn = page.get_by_test_id("member-add-btn")
        add_btn.wait_for(state="visible", timeout=5000)

        # ── Step 5: Invite member by email ───────────────────────────────────
        print(f"[5] UI: add member '{INVITEE_EMAIL}'")
        email_input.fill(INVITEE_EMAIL)
        snap(page, "t48_02_email_filled")

        with page.expect_response("**/api/v1/workspaces/*/members") as resp_info:
            add_btn.click()
        resp = resp_info.value
        assert resp.status == 201, f"Add member API returned {resp.status}"

        # Wait for the new member row to appear in the list
        member_row = page.get_by_test_id(f"member-row-{invitee_user_id}")
        member_row.wait_for(state="visible", timeout=5000)
        snap(page, "t48_03_member_added")
        print("    UI: member row visible")

        # ── Step 6: BE verify — member listed via API ────────────────────────
        print("[6] BE verify: member in workspace members list")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200, f"list members: {r.status_code}"
        members = r.json()
        invitee = next((m for m in members if m["user_id"] == invitee_user_id), None)
        assert invitee is not None, f"Invitee not in members: {[m['user_id'] for m in members]}"
        assert invitee["role"] == "member", f"Expected role 'member', got '{invitee['role']}'"
        assert invitee["email"] == INVITEE_EMAIL, f"Email mismatch: {invitee['email']}"
        print(f"    BE: found member role={invitee['role']} email={invitee['email']}")

        # ── Step 7: UI — invite non-existent email → error ───────────────────
        print("[7] UI: invite non-existent email → error")
        email_input.fill("nonexistent-user-xyz@nowhere.invalid")
        with page.expect_response("**/api/v1/workspaces/*/members") as resp_info:
            add_btn.click()
        assert resp_info.value.status == 404

        error_el = page.get_by_test_id("member-add-error")
        error_el.wait_for(state="visible", timeout=5000)
        error_text = error_el.text_content() or ""
        assert "not found" in error_text.lower() or "register" in error_text.lower(), (
            f"Expected 'not found' error, got: {error_text}"
        )
        snap(page, "t48_04_not_found_error")
        print(f"    error displayed: {error_text}")

        # ── Step 8: UI — invite already-added member → conflict error ────────
        print("[8] UI: invite already-added member → conflict error")
        email_input.fill("")
        email_input.fill(INVITEE_EMAIL)
        with page.expect_response("**/api/v1/workspaces/*/members") as resp_info:
            add_btn.click()
        assert resp_info.value.status == 409

        # FE clears addError on submit then sets new error after response
        error_el = page.get_by_test_id("member-add-error")
        error_el.wait_for(state="visible", timeout=5000)
        error_text = error_el.text_content() or ""
        assert "already" in error_text.lower() or "conflict" in error_text.lower(), (
            f"Expected 'already a member' error, got: {error_text}"
        )
        snap(page, "t48_05_conflict_error")
        print(f"    error displayed: {error_text}")

        browser.close()

    # ── Teardown ─────────────────────────────────────────────────────────────
    print("[9] Teardown: delete workspace + invitee user")
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)
    assert r.status_code == 204, f"Delete workspace failed: {r.status_code}"
    r = api("DELETE", f"/api/v1/admin/users/{INVITEE_EMAIL}", admin_token)
    if r.status_code not in (204, 404):
        print(f"    WARN: delete user returned {r.status_code}")

    print("PASS: e2e_test_workspace_member_invite")


if __name__ == "__main__":
    run()
