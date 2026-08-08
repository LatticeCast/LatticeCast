"""E2E: workspace access-level changes and last-owner protection.

Verifies the V33 read/write/owner contract through the member-management UI
and confirms every mutation through the backend member list.

Run:
    docker compose exec -T e2e pytest workspace/test_member_level.py -v [--snapshot]
"""

import time

from e2e_base import BASE, api

SCREENSHOT_DIR = "/output"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)


def test_member_level_change(authed_page, workspace, admin_token, snapshot):
    """Change write -> owner -> read and keep the last owner intact."""
    page = authed_page
    ws_id, ws_name = workspace
    suffix = int(time.time() * 1000) % 10_000_000
    member_email = f"e2e-level-{suffix}@e2e.local"

    print(f"[1] Setup: create member user '{member_email}'")
    api("DELETE", f"/api/v1/admin/users/{member_email}", admin_token)
    response = api(
        "POST",
        "/api/v1/admin/users",
        admin_token,
        json={"email": member_email, "role": "user"},
    )
    assert response.status_code == 201, (
        f"create member: {response.status_code} {response.text[:200]}"
    )
    member_user_id = response.json()["user_id"]

    try:
        print("[2] Setup: add member with write access")
        response = api(
            "POST",
            f"/api/v1/workspaces/{ws_id}/members",
            admin_token,
            json={"user_email": member_email, "level": "write"},
        )
        assert response.status_code == 201, (
            f"add member: {response.status_code} {response.text[:200]}"
        )
        assert response.json()["level"] == "write"

        print(f"[3] UI: navigate to /{ws_name}/members")
        page.goto(f"{BASE}/{ws_name}/members", wait_until="networkidle")
        assert "/login" not in page.url, "Redirected to /login — auth failed"
        page.get_by_test_id("members-heading").wait_for(state="visible", timeout=10000)

        level_select = page.get_by_test_id(f"level-select-{member_user_id}")
        level_select.wait_for(state="visible", timeout=5000)
        assert level_select.input_value() == "write"
        snap(page, "member_level_01_write", snapshot)

        print("[4] UI: change access level write -> owner")
        with page.expect_response("**/api/v1/workspaces/*/members/*") as response_info:
            level_select.select_option("owner")
        assert response_info.value.status == 200
        assert level_select.input_value() == "owner"

        response = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert response.status_code == 200
        members = response.json()
        target = next(member for member in members if member["user_id"] == member_user_id)
        assert target["level"] == "owner"
        snap(page, "member_level_02_owner", snapshot)

        print("[5] UI: change access level owner -> read")
        with page.expect_response("**/api/v1/workspaces/*/members/*") as response_info:
            level_select.select_option("read")
        assert response_info.value.status == 200
        assert level_select.input_value() == "read"

        response = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert response.status_code == 200
        members = response.json()
        target = next(member for member in members if member["user_id"] == member_user_id)
        assert target["level"] == "read"
        snap(page, "member_level_03_read", snapshot)

        print("[6] UI: attempt to demote the last owner")
        admin_member = next(member for member in members if member["level"] == "owner")
        admin_user_id = admin_member["user_id"]
        admin_level_select = page.get_by_test_id(f"level-select-{admin_user_id}")
        admin_level_select.wait_for(state="visible", timeout=5000)

        with page.expect_response("**/api/v1/workspaces/*/members/*") as response_info:
            admin_level_select.select_option("write")
        assert response_info.value.status == 400

        error = page.get_by_test_id("members-error")
        error.wait_for(state="visible", timeout=5000)
        assert "last owner" in (error.text_content() or "").lower()
        assert admin_level_select.input_value() == "owner"

        response = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert response.status_code == 200
        admin_member = next(
            member for member in response.json() if member["user_id"] == admin_user_id
        )
        assert admin_member["level"] == "owner"
        snap(page, "member_level_04_last_owner_blocked", snapshot)
    finally:
        response = api("DELETE", f"/api/v1/admin/users/{member_email}", admin_token)
        assert response.status_code in (204, 404)
