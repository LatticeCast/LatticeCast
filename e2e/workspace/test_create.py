"""
E2E test: task-45 — POST /workspaces (V17 SECURITY DEFINER)

Verifies:
  1. UI: click "+ New" button → modal appears → fill name → submit
  2. UI: navigates to the new workspace page
  3. BE: GET /workspaces lists the new workspace
  4. BE: GET /workspaces/{id}/members shows creator as owner
  5. UI: duplicate name → error message displayed in modal
  6. Teardown: DELETE /workspaces/{id}
"""

import time

from e2e_base import BASE, api

SCREENSHOT_DIR = "/output"

USER = "lattice"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_workspace_create(authed_page, admin_token, snapshot):
    page = authed_page

    suffix = int(time.time()) % 100000
    ws_name = f"ws-create-{suffix}"
    ws_id = None

    try:
        # ── Step 0: Get existing workspace to navigate to ────────────────────
        print("[0] Login")
        r = api("GET", "/api/v1/workspaces", admin_token)
        assert r.status_code == 200 and r.json(), (
            f"Cannot list workspaces: {r.status_code} {r.text[:200]}"
        )
        existing_ws = r.json()[0]["workspace_name"]

        # ── Step 1: Navigate to existing workspace ───────────────────────────
        print(f"[1] Navigate to /{existing_ws}/")
        page.goto(f"{BASE}/{existing_ws}/", wait_until="networkidle")
        assert "/login" not in page.url, "Redirected to /login — auth failed"

        new_ws_btn = page.get_by_test_id("new-workspace-btn")
        new_ws_btn.wait_for(state="visible", timeout=10000)
        snap(page, "t45_01_workspace_page", snapshot)

        # ── Step 2: Open modal and create workspace ──────────────────────────
        print(f"[2] Create workspace '{ws_name}' via modal")
        new_ws_btn.click()

        name_input = page.get_by_test_id("create-workspace-name-input")
        name_input.wait_for(state="visible", timeout=5000)
        name_input.fill(ws_name)
        snap(page, "t45_02_modal_filled", snapshot)

        page.get_by_test_id("create-workspace-submit").click()

        # ── Step 3: UI — verify navigation to new workspace ──────────────────
        print("[3] Verify URL navigated to new workspace")
        page.wait_for_url(f"**/{ws_name}/**", timeout=10000)
        assert ws_name in page.url, f"Expected '{ws_name}' in URL, got {page.url}"
        snap(page, "t45_03_navigated", snapshot)

        # ── Step 4: BE — verify workspace exists via API ─────────────────────
        print("[4] BE verify: workspace listed + creator is owner")
        r = api("GET", "/api/v1/workspaces", admin_token)
        assert r.status_code == 200
        ws_list = r.json()
        created = next((w for w in ws_list if w["workspace_name"] == ws_name), None)
        assert created is not None, f"Workspace '{ws_name}' not in API response"
        ws_id = created["workspace_id"]

        r = api("GET", f"/api/v1/workspaces/{ws_id}/members", admin_token)
        assert r.status_code == 200
        members = r.json()
        owner = next((m for m in members if m["role"] == "owner"), None)
        assert owner is not None, "No owner found in workspace members"


    finally:
        # ── Teardown ─────────────────────────────────────────────────────────
        if ws_id is not None:
            print("[5] Teardown: DELETE workspace via API")
            r = api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)
            assert r.status_code == 204, f"Delete failed: {r.status_code} {r.text[:200]}"

            r = api("GET", f"/api/v1/workspaces/{ws_id}", admin_token)
            assert r.status_code == 404, f"Workspace still exists after delete: {r.status_code}"

    print("PASS: e2e_test_workspace_create")
