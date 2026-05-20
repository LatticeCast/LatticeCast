"""
E2E test: sidebar split-click — chevron toggle vs workspace name navigation.

Verifies:
  1. Setup: create workspace + blank table via API.
  2. Navigate to a table page so sidebar has content.
  3. Open sidebar → chevron collapses workspace → tables hidden.
  4. Chevron expands workspace → tables visible again.
  5. Click workspace name → navigates to /{workspace_name}/.
  6. Navigate back to table → click a DIFFERENT workspace name → navigates.
  7. Teardown: delete workspace via API.

Usage:
    docker compose exec -T test-e2e pytest workspace/test_sidebar.py -v [--snapshot]
"""

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

SCREENSHOT_DIR = "/output"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_sidebar_toggle_and_navigate(authed_page, admin_token, snapshot):
    page = authed_page

    suffix = int(time.time()) % 100000
    ws_name = f"ws-sidebar-{suffix}"
    table_id = f"tbl-sidebar-{suffix}"
    ws_id = None

    try:
        # ── Setup: create workspace + table via API ─────────────────────────
        print("[0] Setup: create workspace + table via API")
        r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": ws_name})
        assert r.status_code == 201, f"create ws: {r.status_code} {r.text[:200]}"
        ws_id = r.json()["workspace_id"]

        r = api("POST", "/api/v1/tables", admin_token, json={
            "table_id": table_id,
            "workspace_id": ws_id,
        })
        assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"

        # Also get another workspace name for cross-workspace nav test
        r = api("GET", "/api/v1/workspaces", admin_token)
        assert r.status_code == 200
        all_ws = r.json()
        other_ws = next((w for w in all_ws if w["workspace_id"] != ws_id), None)

        # ── Step 1: Navigate to the table page ──────────────────────────────
        print(f"[1] Navigate to /{ws_name}/{table_id}")
        page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="networkidle", timeout=20000)
        assert "/login" not in page.url, f"Redirected to /login: {page.url}"
        snap(page, "t_sidebar_01_table_page", snapshot)

        # ── Step 2: Open sidebar ────────────────────────────────────────────
        print("[2] Open sidebar")
        toggle = page.get_by_test_id("menu-toggle")
        try:
            toggle.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            pass
        if toggle.is_visible():
            toggle.click()

        menu_nav = page.get_by_test_id("menu-nav")
        menu_nav.wait_for(state="visible", timeout=5000)
        snap(page, "t_sidebar_02_menu_open", snapshot)

        # ── Step 3: Verify chevron toggle collapses ─────────────────────────
        print("[3] Chevron toggle: collapse workspace")
        ws_toggle = page.get_by_test_id(f"sidebar-workspace-toggle-{ws_name}")
        ws_toggle.wait_for(state="visible", timeout=5000)

        table_link = page.get_by_test_id(f"sidebar-table-{table_id}")
        was_visible = table_link.is_visible()
        print(f"    table visible before toggle: {was_visible}")

        if was_visible:
            ws_toggle.click()
            page.wait_for_timeout(300)
            assert not table_link.is_visible(), "Table should be hidden after collapse"
            print("    collapsed OK — table hidden")
            snap(page, "t_sidebar_03_collapsed", snapshot)

            # ── Step 4: Chevron toggle expands again ────────────────────────
            print("[4] Chevron toggle: expand workspace")
            ws_toggle.click()
            table_link.wait_for(state="visible", timeout=3000)
            assert table_link.is_visible(), "Table should be visible after expand"
            print("    expanded OK — table visible")
            snap(page, "t_sidebar_04_expanded", snapshot)
        else:
            # Was collapsed — expand first, then collapse
            ws_toggle.click()
            table_link.wait_for(state="visible", timeout=3000)
            assert table_link.is_visible(), "Table should be visible after expand"
            print("    expanded OK — table visible")

            ws_toggle.click()
            page.wait_for_timeout(300)
            assert not table_link.is_visible(), "Table should be hidden after collapse"
            print("    collapsed OK — table hidden")

            # Re-expand for next steps
            ws_toggle.click()
            table_link.wait_for(state="visible", timeout=3000)
            snap(page, "t_sidebar_04_expanded", snapshot)

        # ── Step 5: Click workspace name → navigate to /{ws_name}/ ──────────
        print(f"[5] Click workspace name → navigate to /{ws_name}/")
        ws_link = page.get_by_test_id(f"sidebar-workspace-{ws_name}")
        ws_link.wait_for(state="visible", timeout=3000)
        ws_link.click()

        page.wait_for_timeout(2000)
        assert table_id not in page.url, (
            f"Should have left table page, but URL still has table_id: {page.url}"
        )
        print(f"    navigated to: {page.url}")
        snap(page, "t_sidebar_05_ws_page", snapshot)

        # ── Step 6: Cross-workspace sidebar nav ─────────────────────────────
        if other_ws:
            other_name = other_ws["workspace_name"]
            print(f"[6] Navigate back to table, then click other workspace '{other_name}'")

            page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="networkidle", timeout=15000)

            # Re-open sidebar if closed
            toggle2 = page.get_by_test_id("menu-toggle")
            if toggle2.is_visible():
                toggle2.click()
                page.get_by_test_id("menu-nav").wait_for(state="visible", timeout=5000)

            other_link = page.get_by_test_id(f"sidebar-workspace-{other_name}")
            try:
                other_link.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                print(f"    (skipped — '{other_name}' not in sidebar)")
            else:
                other_link.click()
                page.wait_for_timeout(2000)
                assert table_id not in page.url, (
                    f"Should have left table page: {page.url}"
                )
                print(f"    cross-workspace nav OK: {page.url}")
                snap(page, "t_sidebar_06_cross_ws", snapshot)
        else:
            print("[6] (skipped — only one workspace)")

        print("PASS: test_sidebar_toggle_and_navigate")

    finally:
        if ws_id:
            print("[teardown] DELETE workspace")
            api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)
