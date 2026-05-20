"""E2E test: last-clicked view sticks across navigation.

Topic: switching to a view sets it as the default so that navigating away
       and back (without ?view= in the URL) restores the same view.

Flow:
  Setup — login, create fresh workspace + test table + Kanban + Timeline views.
  Step 1 — load table page; verify Schema tab is active (default_view=null).
  Step 2 — click Kanban tab; wait for PATCH /schema; API + UI assert.
  Step 3 — navigate away (workspace root); navigate back (no ?view=); assert Kanban still active.
  Step 4 — click Timeline tab; wait for PATCH /schema; API + UI assert.
  Step 5 — navigate away; navigate back; assert Timeline still active.
  Teardown — DELETE workspace (cascades to table).

Cross-view coverage: Kanban + Timeline (two view types) per e2e skill rules.

Usage:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest table_views/test_views_default.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, login, seed_login_info


SCREENSHOT_DIR = "/output"


def _get_table(table_id: str, token: str) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    if r.status_code != 200:
        pytest.fail(f"GET /tables/{table_id} failed {r.status_code}: {r.text[:200]}")
    return r.json()


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def _goto_table(page, ws_id: str, table_id: str, timeout: int = 20000) -> None:
    """Navigate to the table page and wait for view tabs to render."""
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=timeout)
    except PlaywrightTimeout:
        pytest.fail(f"View tabs did not load for table {table_id!r}")


def _wait_tab_active(page, view_name: str, timeout: int = 8000) -> None:
    """Wait until the view tab shows the active (blue) state."""
    try:
        page.wait_for_function(
            f"""() => {{
                const btn = document.querySelector('[data-testid="view-tab-{view_name}"]');
                return btn && btn.className.includes('text-blue-600');
            }}""",
            timeout=timeout,
        )
    except PlaywrightTimeout:
        cls = page.locator(f'[data-testid="view-tab-{view_name}"]').get_attribute("class") or ""
        pytest.fail(f"Tab '{view_name}' not active after {timeout}ms — class: {cls}")


def _assert_tab_active(page, view_name: str) -> None:
    cls = page.locator(f'[data-testid="view-tab-{view_name}"]').get_attribute("class") or ""
    assert "text-blue-600" in cls, f"Tab '{view_name}' not active; class={cls!r}"


def _assert_tab_inactive(page, view_name: str) -> None:
    cls = page.locator(f'[data-testid="view-tab-{view_name}"]').get_attribute("class") or ""
    assert "text-blue-600" not in cls, f"Tab '{view_name}' should not be active; class={cls!r}"


def test_views_default(browser, admin_token, snapshot) -> None:
    token = admin_token
    _TS = int(time.time())
    WS_NAME = f"e2e-vd-{_TS}"
    TABLE_ID = f"e2e-vd-tbl-{_TS}"

    # ── Pre-flight: login + create workspace + table + views ─────────────────
    print("[0] Pre-flight: create workspace + table + views via API")

    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_id = str(r.json()["workspace_id"])
    print(f"[setup] workspace {WS_NAME!r} → id={ws_id}")

    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_id})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"

    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token, json={"name": "Kanban", "type": "kanban"})
    assert r.status_code == 201, f"create Kanban view: {r.status_code} {r.text[:200]}"
    schema = r.json()
    kanban_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Kanban")

    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token, json={"name": "Timeline", "type": "timeline"})
    assert r.status_code == 201, f"create Timeline view: {r.status_code} {r.text[:200]}"
    schema = r.json()
    timeline_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Timeline")

    print(f"[setup] table={TABLE_ID!r} kanban={kanban_view_id} timeline={timeline_view_id}")

    # Verify initial default_view is null (fresh table)
    tbl = _get_table(TABLE_ID, token)
    assert tbl.get("default_view") is None, \
        f"initial default_view={tbl['default_view']!r}, expected null"
    print("[ok] initial default_view is null")

    try:
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, "lattice", role="admin")

        # ── Step 1: Load table page; Schema tab active by default ─────────────
        print("[1] Load table page; verify Schema tab active")
        _goto_table(page, ws_id, TABLE_ID)
        snap(page, "vd_01_initial_load", snapshot)

        _wait_tab_active(page, "Schema")
        _assert_tab_inactive(page, "Kanban")
        print("[ok] step1: Schema active, Kanban inactive")

        # ── Step 2: Click Kanban tab; verify default_view persisted ──────────
        print("[2] Click Kanban tab; wait for PATCH /schema")
        with page.expect_response(
            lambda r: f"/tables/{TABLE_ID}/schema" in r.url and r.request.method == "PATCH",
            timeout=8000,
        ) as resp_info:
            page.locator('[data-testid="view-tab-Kanban"]').click()
        patch_resp = resp_info.value
        assert patch_resp.status == 200, f"PATCH /schema returned {patch_resp.status}"
        print("[ok] step2: PATCH /schema returned 200")

        snap(page, "vd_02_kanban_clicked", snapshot)

        _assert_tab_active(page, "Kanban")
        _assert_tab_inactive(page, "Schema")
        print("[ok] step2: Kanban active, Schema inactive")

        tbl = _get_table(TABLE_ID, token)
        assert tbl.get("default_view") == kanban_view_id, \
            f"expected default_view={kanban_view_id}, got {tbl.get('default_view')}"
        print(f"[ok] step2: API default_view={kanban_view_id}")

        # ── Step 3: Navigate away; navigate back; verify Kanban restored ──────
        print("[3] Navigate away to workspace root; navigate back; assert Kanban still active")
        page.goto(f"{BASE}/{ws_id}", wait_until="domcontentloaded", timeout=15000)
        _goto_table(page, ws_id, TABLE_ID)

        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        snap(page, "vd_03_back_after_kanban", snapshot)

        _wait_tab_active(page, "Kanban")
        _assert_tab_inactive(page, "Schema")
        print("[ok] step3: Kanban persists after navigation")

        tbl = _get_table(TABLE_ID, token)
        assert tbl.get("default_view") == kanban_view_id, \
            f"step3: expected {kanban_view_id}, got {tbl.get('default_view')}"
        print("[ok] step3: API default_view unchanged")

        # ── Step 4: Click Timeline tab; verify default_view persisted ─────────
        print("[4] Click Timeline tab; wait for PATCH /schema")
        with page.expect_response(
            lambda r: f"/tables/{TABLE_ID}/schema" in r.url and r.request.method == "PATCH",
            timeout=8000,
        ) as resp_info:
            page.locator('[data-testid="view-tab-Timeline"]').click()
        patch_resp = resp_info.value
        assert patch_resp.status == 200, f"PATCH /schema returned {patch_resp.status}"
        print("[ok] step4: PATCH /schema returned 200")

        snap(page, "vd_04_timeline_clicked", snapshot)

        _assert_tab_active(page, "Timeline")
        _assert_tab_inactive(page, "Kanban")
        print("[ok] step4: Timeline active, Kanban inactive")

        tbl = _get_table(TABLE_ID, token)
        assert tbl.get("default_view") == timeline_view_id, \
            f"expected default_view={timeline_view_id}, got {tbl.get('default_view')}"
        print(f"[ok] step4: API default_view={timeline_view_id}")

        # ── Step 5: Navigate away; navigate back; verify Timeline restored ─────
        print("[5] Navigate away; navigate back; assert Timeline still active")
        page.goto(f"{BASE}/{ws_id}", wait_until="domcontentloaded", timeout=15000)
        _goto_table(page, ws_id, TABLE_ID)

        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        snap(page, "vd_05_back_after_timeline", snapshot)

        _wait_tab_active(page, "Timeline")
        _assert_tab_inactive(page, "Kanban")
        print("[ok] step5: Timeline persists after navigation")

        tbl = _get_table(TABLE_ID, token)
        assert tbl.get("default_view") == timeline_view_id, \
            f"step5: expected {timeline_view_id}, got {tbl.get('default_view')}"
        print("[ok] step5: API default_view unchanged")

        snap(page, "vd_06_final", snapshot)
        page.close()

    finally:
        # ── Teardown ──────────────────────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"[warn] teardown DELETE workspace {ws_id!r}: {r.status_code}")
        else:
            print(f"[teardown] workspace {ws_id!r} deleted")

    print("\n=== PASSED — test_views_default ===")
