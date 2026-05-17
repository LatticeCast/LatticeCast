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
    docker compose exec -T test-e2e pytest workspace/test_member_invite.py -v [--snapshot]
"""

import time

from e2e_base import BASE, api

SCREENSHOT_DIR = "/output"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_member_invite(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    ws_id, ws_name = workspace
    suffix = int(time.time()) % 100000
    invitee_email = f"e2e-invite-{suffix}@e2e.local"

    # ── Setup: create invitee user ───────────────────────────────────────────
    print(f"[2] Setup: create invitee user '{invitee_email}'")
    api("DELETE", f"/api/v1/admin/users/{invitee_email}", admin_token)
    r = api("POST", "/api/v1/admin/users", admin_token, json={"email": invitee_email, "role": "user"})
    assert r.status_code == 201, f"create invitee: {r.status_code} {r.text[:200]}"
    invitee_user_id = r.json()["user_id"]
    print(f"    invitee user_id={invitee_user_id}")

    try:
        # ── Step 3: Navigate to members page ─────────────────────────────────
        print(f"[3] UI: navigate to /{ws_name}/members")
        page.goto(f"{BASE}/{ws_name}/members", wait_until="networkidle")
        assert "/login" not in page.url, "Redirected to /login — auth failed"

        heading = page.get_by_test_id("members-heading")
        heading.wait_for(state="visible", timeout=10000)
        snap(page, "t48_01_members_page", snapshot)

        # ── Step 4: Verify Add Member panel visible (owner) ──────────────────
        print("[4] UI: verify Add Member panel visible")
        email_input = page.get_by_test_id("member-email-input")
        email_input.wait_for(state="visible", timeout=5000)
        add_btn = page.get_by_test_id("member-add-btn")
        add_btn.wait_for(state="visible", timeout=5000)

        # ── Step 5: Invite member by email ───────────────────────────────────
        print(f"[5] UI: add member '{invitee_email}'")
        email_input.fill(invitee_email)
        snap(page, "t48_02_email_filled", snapshot)

        with page.expect_response("**/api/v1/workspaces/*/members") as resp_info:
            add_btn.click()
        resp = resp_info.value
        assert resp.status == 201, f"Add member API returned {resp.status}"

        # Wait for the new member row to appear in the list
        member_row = page.get_by_test_id(f"member-row-{invitee_user_id}")
        member_row.wait_for(state="visible", timeout=5000)
        snap(page, "t48_03_member_added", snapshot)
        print("    UI: member row visible")

        # ── Step 6: BE verify — member listed via API ────────────────────────
        print("[6] BE verify: member in workspace members list")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200, f"list members: {r.status_code}"
        members = r.json()
        invitee = next((m for m in members if m["user_id"] == invitee_user_id), None)
        assert invitee is not None, f"Invitee not in members: {[m['user_id'] for m in members]}"
        assert invitee["role"] == "member", f"Expected role 'member', got '{invitee['role']}'"
        assert invitee["email"] == invitee_email, f"Email mismatch: {invitee['email']}"
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
        snap(page, "t48_04_not_found_error", snapshot)
        print(f"    error displayed: {error_text}")

        # ── Step 8: UI — invite already-added member → conflict error ────────
        print("[8] UI: invite already-added member → conflict error")
        email_input.fill("")
        email_input.fill(invitee_email)
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
        snap(page, "t48_05_conflict_error", snapshot)
        print(f"    error displayed: {error_text}")

    finally:
        # ── Teardown: invitee user (workspace cleanup handled by fixture) ────
        print("[9] Teardown: delete invitee user")
        r = api("DELETE", f"/api/v1/admin/users/{invitee_email}", admin_token)
        if r.status_code not in (204, 404):
            print(f"    WARN: delete user returned {r.status_code}")

    print("PASS: e2e_test_workspace_member_invite")
