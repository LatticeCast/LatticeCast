"""
E2E test: task-49 — role change owner↔member

Verifies:
  1. Setup: create workspace + second user; add second user as member.
  2. UI: owner sees role dropdown for the member.
  3. UI: change member → owner via dropdown; API response 200.
  4. BE: GET members confirms role=owner for promoted user.
  5. UI: change back owner → member via dropdown; API response 200.
  6. BE: GET members confirms role=member for demoted user.
  7. UI: attempt to demote the LAST owner → error displayed.
  8. BE: role unchanged (still owner) after failed demotion.
  9. Teardown: delete workspace + test user.
"""

import time

import pytest

from e2e_base import BASE, api, login, seed_login_info

SCREENSHOT_DIR = "/output"
ADMIN_USER = "lattice"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_member_role_change(authed_page, admin_token, snapshot):
    """Role change owner↔member with last-owner protection."""
    page = authed_page

    suffix = int(time.time()) % 100000
    ws_name = f"ws-role-{suffix}"
    member_email = f"e2e-role-{suffix}@e2e.local"

    # ── Setup: create workspace ──────────────────────────────────────────────
    print(f"[1] Setup: create workspace '{ws_name}'")
    r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": ws_name})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_id = r.json()["workspace_id"]

    try:
        # ── Setup: create member user ────────────────────────────────────────
        print(f"[2] Setup: create member user '{member_email}'")
        api("DELETE", f"/api/v1/admin/users/{member_email}", admin_token)
        r = api("POST", "/api/v1/admin/users", admin_token, json={"email": member_email, "role": "user"})
        assert r.status_code == 201, f"create member user: {r.status_code} {r.text[:200]}"
        member_user_id = r.json()["user_id"]
        print(f"    member user_id={member_user_id}")

        # ── Setup: add member to workspace ───────────────────────────────────
        print("[3] Setup: add member to workspace")
        r = api("POST", f"/api/v1/workspaces/{ws_id}/members", admin_token,
                json={"user_email": member_email, "role": "member"})
        assert r.status_code == 201, f"add member: {r.status_code} {r.text[:200]}"

        # ── Step 4: Navigate to members page ─────────────────────────────────
        print(f"[4] UI: navigate to /{ws_name}/members")
        page.goto(f"{BASE}/{ws_name}/members", wait_until="networkidle")
        assert "/login" not in page.url, "Redirected to /login — auth failed"

        heading = page.get_by_test_id("members-heading")
        heading.wait_for(state="visible", timeout=10000)
        snap(page, "t49_01_members_page", snapshot)

        # ── Step 5: Verify role dropdown visible for member ──────────────────
        print("[5] UI: verify role dropdown for member")
        role_select = page.get_by_test_id(f"role-select-{member_user_id}")
        role_select.wait_for(state="visible", timeout=5000)
        current_value = role_select.input_value()
        assert current_value == "member", f"Expected initial role 'member', got '{current_value}'"
        print(f"    role dropdown shows: {current_value}")

        # ── Step 6: Promote member → owner ───────────────────────────────────
        print("[6] UI: change role member → owner")
        with page.expect_response("**/api/v1/workspaces/*/members/*") as resp_info:
            role_select.select_option("owner")
        resp = resp_info.value
        assert resp.status == 200, f"PUT role change returned {resp.status}"
        snap(page, "t49_02_promoted_to_owner", snapshot)

        # Verify UI updated
        updated_value = role_select.input_value()
        assert updated_value == "owner", f"UI not updated after promote: got '{updated_value}'"
        print(f"    UI shows: {updated_value}")

        # ── Step 7: BE verify — role is owner ────────────────────────────────
        print("[7] BE verify: member role is now 'owner'")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200, f"list members: {r.status_code}"
        members = r.json()
        target = next((m for m in members if m["user_id"] == member_user_id), None)
        assert target is not None, f"Member not in list: {[m['user_id'] for m in members]}"
        assert target["role"] == "owner", f"BE role expected 'owner', got '{target['role']}'"
        print(f"    BE: role={target['role']}")

        # ── Step 8: Demote owner → member ────────────────────────────────────
        print("[8] UI: change role owner → member")
        with page.expect_response("**/api/v1/workspaces/*/members/*") as resp_info:
            role_select.select_option("member")
        resp = resp_info.value
        assert resp.status == 200, f"PUT role change returned {resp.status}"
        snap(page, "t49_03_demoted_to_member", snapshot)

        updated_value = role_select.input_value()
        assert updated_value == "member", f"UI not updated after demote: got '{updated_value}'"
        print(f"    UI shows: {updated_value}")

        # ── Step 9: BE verify — role is member again ─────────────────────────
        print("[9] BE verify: member role is now 'member'")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200
        members = r.json()
        target = next((m for m in members if m["user_id"] == member_user_id), None)
        assert target is not None
        assert target["role"] == "member", f"BE role expected 'member', got '{target['role']}'"
        print(f"    BE: role={target['role']}")

        # ── Step 10: Last-owner demotion blocked ─────────────────────────────
        print("[10] UI: attempt to demote last owner (admin) → error")
        # Get admin user_id from members list
        admin_member = next((m for m in members if m["role"] == "owner"), None)
        assert admin_member is not None, "No owner found in members list"
        admin_user_id = admin_member["user_id"]

        admin_role_select = page.get_by_test_id(f"role-select-{admin_user_id}")
        admin_role_select.wait_for(state="visible", timeout=5000)

        with page.expect_response("**/api/v1/workspaces/*/members/*") as resp_info:
            admin_role_select.select_option("member")
        resp = resp_info.value
        assert resp.status == 400, f"Expected 400 for last-owner demotion, got {resp.status}"
        snap(page, "t49_04_last_owner_error", snapshot)

        # Verify error message displayed
        error_el = page.get_by_test_id("members-error")
        error_el.wait_for(state="visible", timeout=5000)
        error_text = error_el.text_content() or ""
        assert "last owner" in error_text.lower() or "cannot demote" in error_text.lower(), (
            f"Expected 'last owner' error, got: {error_text}"
        )
        print(f"    error displayed: {error_text}")

        # ── Step 11: BE verify — admin still owner after failed demotion ─────
        print("[11] BE verify: admin still owner after blocked demotion")
        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200
        members = r.json()
        admin_m = next((m for m in members if m["user_id"] == admin_user_id), None)
        assert admin_m is not None
        assert admin_m["role"] == "owner", f"Admin role expected 'owner', got '{admin_m['role']}'"
        print(f"    BE: admin role={admin_m['role']}")

        # Verify UI reverted the dropdown
        admin_role_value = admin_role_select.input_value()
        assert admin_role_value == "owner", f"UI should revert to 'owner', got '{admin_role_value}'"
        print(f"    UI reverted: {admin_role_value}")

    finally:
        # ── Teardown ─────────────────────────────────────────────────────────
        print("[12] Teardown: delete workspace + member user")
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)
        assert r.status_code == 204, f"Delete workspace failed: {r.status_code}"
        r = api("DELETE", f"/api/v1/admin/users/{member_email}", admin_token)
        if r.status_code not in (204, 404):
            print(f"    WARN: delete user returned {r.status_code}")

    print("PASS: e2e_test_workspace_member_role")
