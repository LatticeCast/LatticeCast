"""E2E: PostgreSQL RLS is the only authorization boundary.

Story 53 removed every backend permission question — `check_workspace_permission`
is revoked from the `app` role (V53), so what a caller may see or change is
decided by the policies in V52 alone. This test pins that boundary from the
outside, with one owner and one invited `read`-level member:

  * the member's /sidebar carries the shared workspace and `level == "read"`,
    and the browser renders it (with no owner-only affordance);
  * `read` does not gate mutation: rename and table creation are refused;
  * a workspace the member was never invited to answers 404, not 403, so its
    existence stays undisclosed;
  * the roster is owner-only — the owner sees both people, the member is
    refused rather than shown anyone else's grants.

Run:
    docker compose exec -T e2e pytest workspace/test_rls_only_authorization.py -v [--snapshot]
"""

import time

from e2e_base import BASE, api, login, seed_login_info

SCREENSHOT_DIR = "/output"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)


def test_rls_only_authorization(page, workspace, admin_token, snapshot):
    shared_ws_id, shared_ws_name = workspace
    suffix = int(time.time() * 1000) % 10_000_000
    member_name = f"e2e-rls-{suffix}"
    member_email = f"{member_name}@e2e.local"
    shared_table_id = f"shared-{suffix}"
    private_ws_name = f"test-ws-private-{suffix}"
    private_table_id = f"private-{suffix}"
    private_ws_id = None

    print(f"[1] Setup: create member user '{member_email}'")
    response = api(
        "POST", "/api/v1/admin/users", admin_token,
        json={"email": member_email, "user_name": member_name, "role": "user"},
    )
    assert response.status_code == 201, (
        f"create member: {response.status_code} {response.text[:200]}"
    )
    member_user_id = response.json()["user_id"]
    member_token = login(member_name)

    try:
        print(f"[2] Setup: owner creates table '{shared_table_id}' in the shared workspace")
        response = api(
            "POST", "/api/v1/tables", admin_token,
            json={"table_id": shared_table_id, "workspace_id": shared_ws_id},
        )
        assert response.status_code == 201, (
            f"create shared table: {response.status_code} {response.text[:200]}"
        )

        print(f"[3] Setup: owner creates un-shared workspace '{private_ws_name}' + table")
        response = api(
            "POST", "/api/v1/workspaces", admin_token,
            json={"workspace_name": private_ws_name},
        )
        assert response.status_code == 201, (
            f"create private workspace: {response.status_code} {response.text[:200]}"
        )
        private_ws_id = response.json()["workspace_id"]
        response = api(
            "POST", "/api/v1/tables", admin_token,
            json={"table_id": private_table_id, "workspace_id": private_ws_id},
        )
        assert response.status_code == 201, (
            f"create private table: {response.status_code} {response.text[:200]}"
        )

        print("[4] Setup: owner invites the member at level 'read'")
        response = api(
            "POST", f"/api/v1/workspaces/{shared_ws_id}/members", admin_token,
            json={"user_email": member_email, "level": "read"},
        )
        assert response.status_code == 201, (
            f"add member: {response.status_code} {response.text[:200]}"
        )
        assert response.json()["level"] == "read"

        # ── API: the member's sidebar payload ────────────────────────────────
        print("[5] API: member GET /sidebar reports the shared workspace at level 'read'")
        response = api("GET", "/api/v1/sidebar", member_token)
        assert response.status_code == 200, (
            f"member sidebar: {response.status_code} {response.text[:200]}"
        )
        payload = response.json()
        sidebar_workspaces = {ws["workspace_id"]: ws for ws in payload["workspaces"]}
        assert shared_ws_id in sidebar_workspaces, (
            f"shared workspace missing from member sidebar: {list(sidebar_workspaces)}"
        )
        assert sidebar_workspaces[shared_ws_id]["level"] == "read", (
            f"expected level 'read', got {sidebar_workspaces[shared_ws_id]['level']!r}"
        )
        assert private_ws_id not in sidebar_workspaces, (
            "un-shared workspace leaked into the member's sidebar"
        )
        member_tables = {
            (t["workspace_id"], t["table_id"]) for t in payload["tables"]
        }
        assert (shared_ws_id, shared_table_id) in member_tables, (
            f"shared table missing from member sidebar: {sorted(member_tables)}"
        )
        assert (private_ws_id, private_table_id) not in member_tables, (
            "un-shared table leaked into the member's sidebar"
        )

        # ── UI: the member's rendered sidebar ────────────────────────────────
        print(f"[6] UI: member opens /{shared_ws_id}/ and the sidebar renders the workspace")
        seed_login_info(page, member_token, member_name, role="user")
        with page.expect_response("**/api/v1/sidebar") as sidebar_info:
            page.goto(f"{BASE}/{shared_ws_id}/", wait_until="networkidle")
        assert sidebar_info.value.status == 200
        assert "/login" not in page.url, f"Redirected to /login: {page.url}"

        page.get_by_test_id("menu-toggle").click()
        page.get_by_test_id("menu-nav").wait_for(state="visible", timeout=10000)

        ws_entry = page.get_by_test_id(f"sidebar-workspace-{shared_ws_id}")
        ws_entry.wait_for(state="visible", timeout=10000)
        assert shared_ws_name in (ws_entry.text_content() or ""), (
            f"sidebar entry text {ws_entry.text_content()!r} lacks {shared_ws_name!r}"
        )

        # The workspace auto-expands because it has a table; the table link is
        # the proof the member reads its contents, and the Members link is
        # rendered only at level 'owner' — its absence is the derived UI for
        # the 'read' level asserted at step 5.
        page.get_by_test_id(f"sidebar-table-{shared_table_id}").wait_for(
            state="visible", timeout=10000
        )
        assert page.get_by_test_id(f"nav-members-{shared_ws_id}").count() == 0, (
            "owner-only Members link rendered for a 'read' member"
        )
        assert page.get_by_test_id(f"sidebar-workspace-{private_ws_id}").count() == 0, (
            "un-shared workspace rendered in the member's sidebar"
        )
        snap(page, "rls_only_01_member_sidebar_read", snapshot)

        # ── 'read' does not gate mutation ────────────────────────────────────
        print("[7] API: member cannot rename the shared workspace")
        response = api(
            "PUT", f"/api/v1/workspaces/{shared_ws_id}", member_token,
            json={"workspace_name": f"{shared_ws_name}-renamed"},
        )
        assert response.status_code == 403, (
            f"expected 403 on rename, got {response.status_code} {response.text[:200]}"
        )
        response = api("GET", f"/api/v1/workspaces/{shared_ws_id}", admin_token)
        assert response.status_code == 200
        assert response.json()["workspace_name"] == shared_ws_name, "workspace was renamed"

        print("[8] API: member cannot create a table in the shared workspace")
        denied_table_id = f"denied-{suffix}"
        response = api(
            "POST", "/api/v1/tables", member_token,
            json={"table_id": denied_table_id, "workspace_id": shared_ws_id},
        )
        assert response.status_code == 403, (
            f"expected 403 on create table, got {response.status_code} {response.text[:200]}"
        )
        response = api("GET", "/api/v1/tables", admin_token)
        assert response.status_code == 200
        owner_table_ids = {
            t["table_id"] for t in response.json() if t["workspace_id"] == shared_ws_id
        }
        assert denied_table_id not in owner_table_ids, (
            f"refused table was created anyway: {sorted(owner_table_ids)}"
        )

        # ── Existence stays undisclosed: 404, never 403 ──────────────────────
        print("[9] API: an un-shared workspace and its table answer 404, not 403")
        response = api(
            "GET",
            f"/api/v1/tables/{private_table_id}?workspace_id={private_ws_id}",
            member_token,
        )
        assert response.status_code == 404, (
            f"expected 404 for unreachable table, got {response.status_code} "
            f"{response.text[:200]}"
        )
        response = api("GET", f"/api/v1/workspaces/{private_ws_id}", member_token)
        assert response.status_code == 404, (
            f"expected 404 for unreachable workspace, got {response.status_code} "
            f"{response.text[:200]}"
        )

        # ── The roster is owner-only ─────────────────────────────────────────
        print("[10] API: owner sees the full roster; the member is refused it")
        response = api("GET", f"/api/v1/workspaces/{shared_ws_id}/members", admin_token)
        assert response.status_code == 200, (
            f"owner roster: {response.status_code} {response.text[:200]}"
        )
        roster = {member["user_id"]: member for member in response.json()}
        assert member_user_id in roster, f"member missing from roster: {list(roster)}"
        assert roster[member_user_id]["level"] == "read"
        owners = [m for m in roster.values() if m["level"] == "owner"]
        assert len(owners) == 1, f"expected exactly one owner, got {owners}"
        assert len(roster) == 2, f"expected owner + member, got {list(roster)}"

        # Reading another member's grants requires 'owner' (llm.user.md), so the
        # route refuses the 'read' member outright rather than answering with a
        # self-only list — strictly less disclosure than RLS alone would give.
        response = api("GET", f"/api/v1/workspaces/{shared_ws_id}/members", member_token)
        assert response.status_code == 403, (
            f"expected 403 on member roster read, got {response.status_code} "
            f"{response.text[:200]}"
        )

        print("[11] UI: after the refusals the member's sidebar is unchanged")
        with page.expect_response("**/api/v1/sidebar") as sidebar_info:
            page.reload(wait_until="networkidle")
        assert sidebar_info.value.status == 200
        page.get_by_test_id("menu-toggle").click()
        ws_entry = page.get_by_test_id(f"sidebar-workspace-{shared_ws_id}")
        ws_entry.wait_for(state="visible", timeout=10000)
        assert shared_ws_name in (ws_entry.text_content() or ""), (
            f"rename took effect in the UI: {ws_entry.text_content()!r}"
        )
        page.get_by_test_id(f"sidebar-table-{shared_table_id}").wait_for(
            state="visible", timeout=10000
        )
        assert page.get_by_test_id(f"sidebar-table-{denied_table_id}").count() == 0, (
            "refused table rendered in the member's sidebar"
        )
        snap(page, "rls_only_02_member_sidebar_after_denials", snapshot)

        print("PASS: test_rls_only_authorization")
    finally:
        print("[teardown] delete member user + un-shared workspace")
        if private_ws_id:
            api("DELETE", f"/api/v1/workspaces/{private_ws_id}", admin_token)
        response = api("DELETE", f"/api/v1/admin/users/{member_email}", admin_token)
        assert response.status_code in (204, 404)
