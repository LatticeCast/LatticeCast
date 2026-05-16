#!/usr/bin/env python3
"""
E2E test: last-clicked view sticks across navigation.

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
    docker compose exec test-e2e python3 /scripts/e2e_test_views_default.py [--snapshot]
"""

import json
import os
import sys
import time
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from e2e_base import install_be_reroute

BASE_URL = os.environ.get("BASE_URL", "http://localhost:13491").rstrip("/")
BROWSER_WS = os.environ.get("BROWSER_WS", "")
SCREENSHOT_DIR = "/output"
ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WS_NAME = f"e2e-vd-{_SUFFIX}"
TABLE_ID = f"e2e-vd-tbl-{_SUFFIX}"


# ── API helpers ───────────────────────────────────────────────────────────────


def _login(user_name: str) -> str:
    """POST /login/password → access_token."""
    r = requests.post(
        f"{BASE_URL}/api/v1/login/password",
        json={"user_name": user_name, "password": ""},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed {r.status_code}: {r.text[:200]}")
    return r.json()["access_token"]


def _api(method: str, path: str, token: str, **kw) -> requests.Response:
    return getattr(requests, method)(
        f"{BASE_URL}/api/v1{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        **kw,
    )


def _setup(token: str) -> tuple[str, int, int]:
    """Create workspace + table + Kanban + Timeline views.

    Returns (workspace_id, kanban_view_id, timeline_view_id).
    """
    r = _api("post", "/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        raise RuntimeError(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = str(r.json()["workspace_id"])

    r = _api("post", "/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_id})
    if r.status_code != 201:
        raise RuntimeError(f"create table: {r.status_code} {r.text[:200]}")

    r = _api("post", f"/tables/{TABLE_ID}/views", token, json={"name": "Kanban", "type": "kanban"})
    if r.status_code != 201:
        raise RuntimeError(f"create Kanban view: {r.status_code} {r.text[:200]}")
    schema = r.json()
    kanban_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Kanban")

    r = _api("post", f"/tables/{TABLE_ID}/views", token, json={"name": "Timeline", "type": "timeline"})
    if r.status_code != 201:
        raise RuntimeError(f"create Timeline view: {r.status_code} {r.text[:200]}")
    schema = r.json()
    timeline_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Timeline")

    print(f"[setup] ws={ws_id!r} table={TABLE_ID!r} kanban={kanban_view_id} timeline={timeline_view_id}")
    return ws_id, kanban_view_id, timeline_view_id


def _teardown(token: str, ws_id: str) -> None:
    r = _api("delete", f"/workspaces/{ws_id}", token)
    if r.status_code not in (200, 204):
        print(f"[warn] teardown DELETE workspace {ws_id!r}: {r.status_code}", file=sys.stderr)
    else:
        print(f"[teardown] workspace {ws_id!r} deleted")


def _get_table(table_id: str, token: str) -> dict:
    r = _api("get", f"/tables/{table_id}", token)
    if r.status_code != 200:
        raise RuntimeError(f"GET /tables/{table_id} failed {r.status_code}: {r.text[:200]}")
    return r.json()


def _snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


# ── UI helpers ────────────────────────────────────────────────────────────────


def _goto_table(page, ws_id: str, table_id: str, timeout: int = 20000) -> None:
    """Navigate to the table page and wait for view tabs to render."""
    page.goto(f"{BASE_URL}/{ws_id}/{table_id}", wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=timeout)
    except PlaywrightTimeout:
        raise AssertionError(f"View tabs did not load for table {table_id!r}")


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
        raise AssertionError(
            f"Tab '{view_name}' not active after {timeout}ms — class: {cls}"
        )


def _assert_tab_active(page, view_name: str) -> None:
    cls = page.locator(f'[data-testid="view-tab-{view_name}"]').get_attribute("class") or ""
    assert "text-blue-600" in cls, f"Tab '{view_name}' not active; class={cls!r}"


def _assert_tab_inactive(page, view_name: str) -> None:
    cls = page.locator(f'[data-testid="view-tab-{view_name}"]').get_attribute("class") or ""
    assert "text-blue-600" not in cls, f"Tab '{view_name}' should not be active; class={cls!r}"


# ── Main test ─────────────────────────────────────────────────────────────────


def run(snapshot: bool = False) -> dict:
    results: dict = {
        "test": "e2e_test_views_default",
        "timestamp": datetime.now().isoformat(),
        "table_id": TABLE_ID,
        "checks": {},
        "passed": False,
    }

    # ── Pre-flight: login + create workspace + table + views ─────────────────
    print("[0] Pre-flight: login and create workspace + table + views via API")
    ws_id: str | None = None
    token: str | None = None
    kanban_view_id: int = 0
    timeline_view_id: int = 0
    try:
        token = _login(ADMIN_USER)
        ws_id, kanban_view_id, timeline_view_id = _setup(token)
    except Exception as exc:
        results["checks"]["setup"] = f"fail: {exc}"
        print(json.dumps(results, indent=2))
        return results
    results["checks"]["setup"] = f"pass: kanban={kanban_view_id} timeline={timeline_view_id}"

    # Verify initial default_view is null (fresh table). API failure aborts.
    tbl = _get_table(TABLE_ID, token)
    if tbl.get("default_view") is not None:
        results["checks"]["initial_default_null"] = f"fail: default_view={tbl['default_view']!r}, expected null"
        print(json.dumps(results, indent=2))
        return results
    results["checks"]["initial_default_null"] = "pass"

    # ── Browser session ───────────────────────────────────────────────────────
    pw = sync_playwright().start()
    browser = pw.chromium.connect(BROWSER_WS) if BROWSER_WS else pw.chromium.launch(headless=True)

    try:
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        install_be_reroute(page)
        # Seed auth in localStorage before any navigation
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.evaluate(
            "(info) => localStorage.setItem('loginInfo', info)",
            json.dumps({
                "provider": "none",
                "accessToken": token,
                "userInfo": {"sub": token, "email": "lattice@example.com", "name": ADMIN_USER},
                "role": "admin",
            }),
        )

        # ── Step 1: Load table page; Schema tab active by default ─────────────
        print("[1] Load table page; verify Schema tab active")
        try:
            _goto_table(page, ws_id, TABLE_ID)
        except AssertionError as exc:
            results["checks"]["step1_page_load"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s1_load", snapshot)
            print(json.dumps(results, indent=2))
            return results

        _snap(page, "vd_01_initial_load", snapshot)

        try:
            _wait_tab_active(page, "Schema")
            _assert_tab_inactive(page, "Kanban")
            results["checks"]["step1_schema_active"] = "pass"
        except AssertionError as exc:
            results["checks"]["step1_schema_active"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s1_schema", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # ── Step 2: Click Kanban tab; verify default_view persisted ──────────
        print("[2] Click Kanban tab; wait for PATCH /schema")
        try:
            with page.expect_response(
                lambda r: f"/tables/{TABLE_ID}/schema" in r.url and r.request.method == "PATCH",
                timeout=8000,
            ) as resp_info:
                page.locator('[data-testid="view-tab-Kanban"]').click()
            patch_resp = resp_info.value
            assert patch_resp.status == 200, f"PATCH /schema returned {patch_resp.status}"
            results["checks"]["step2_patch_schema"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["step2_patch_schema"] = "fail: PATCH /schema timed out after click"
            _snap(page, "vd_FAIL_s2_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results
        except AssertionError as exc:
            results["checks"]["step2_patch_schema"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s2_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results

        _snap(page, "vd_02_kanban_clicked", snapshot)

        try:
            _assert_tab_active(page, "Kanban")
            _assert_tab_inactive(page, "Schema")
            results["checks"]["step2_ui_kanban_active"] = "pass"
        except AssertionError as exc:
            results["checks"]["step2_ui_kanban_active"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s2_ui", snapshot)
            print(json.dumps(results, indent=2))
            return results

        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == kanban_view_id:
            results["checks"]["step2_api_default_view"] = f"pass: default_view={kanban_view_id}"
        else:
            results["checks"]["step2_api_default_view"] = (
                f"fail: expected default_view={kanban_view_id}, got {tbl.get('default_view')}"
            )
            _snap(page, "vd_FAIL_s2_api", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # ── Step 3: Navigate away; navigate back; verify Kanban restored ──────
        print("[3] Navigate away to workspace root; navigate back; assert Kanban still active")
        page.goto(f"{BASE_URL}/{ws_id}", wait_until="domcontentloaded", timeout=15000)
        _goto_table(page, ws_id, TABLE_ID)

        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        _snap(page, "vd_03_back_after_kanban", snapshot)

        try:
            _wait_tab_active(page, "Kanban")
            _assert_tab_inactive(page, "Schema")
            results["checks"]["step3_kanban_persists"] = "pass"
        except AssertionError as exc:
            results["checks"]["step3_kanban_persists"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s3_kanban", snapshot)
            print(json.dumps(results, indent=2))
            return results

        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == kanban_view_id:
            results["checks"]["step3_api_unchanged"] = "pass"
        else:
            results["checks"]["step3_api_unchanged"] = (
                f"fail: expected {kanban_view_id}, got {tbl.get('default_view')}"
            )

        # ── Step 4: Click Timeline tab; verify default_view persisted ─────────
        print("[4] Click Timeline tab; wait for PATCH /schema")
        try:
            with page.expect_response(
                lambda r: f"/tables/{TABLE_ID}/schema" in r.url and r.request.method == "PATCH",
                timeout=8000,
            ) as resp_info:
                page.locator('[data-testid="view-tab-Timeline"]').click()
            patch_resp = resp_info.value
            assert patch_resp.status == 200, f"PATCH /schema returned {patch_resp.status}"
            results["checks"]["step4_patch_schema"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["step4_patch_schema"] = "fail: PATCH /schema timed out after click"
            _snap(page, "vd_FAIL_s4_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results
        except AssertionError as exc:
            results["checks"]["step4_patch_schema"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s4_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results

        _snap(page, "vd_04_timeline_clicked", snapshot)

        try:
            _assert_tab_active(page, "Timeline")
            _assert_tab_inactive(page, "Kanban")
            results["checks"]["step4_ui_timeline_active"] = "pass"
        except AssertionError as exc:
            results["checks"]["step4_ui_timeline_active"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s4_ui", snapshot)
            print(json.dumps(results, indent=2))
            return results

        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == timeline_view_id:
            results["checks"]["step4_api_default_view"] = f"pass: default_view={timeline_view_id}"
        else:
            results["checks"]["step4_api_default_view"] = (
                f"fail: expected default_view={timeline_view_id}, got {tbl.get('default_view')}"
            )
            _snap(page, "vd_FAIL_s4_api", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # ── Step 5: Navigate away; navigate back; verify Timeline restored ─────
        print("[5] Navigate away; navigate back; assert Timeline still active")
        page.goto(f"{BASE_URL}/{ws_id}", wait_until="domcontentloaded", timeout=15000)
        _goto_table(page, ws_id, TABLE_ID)

        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        _snap(page, "vd_05_back_after_timeline", snapshot)

        try:
            _wait_tab_active(page, "Timeline")
            _assert_tab_inactive(page, "Kanban")
            results["checks"]["step5_timeline_persists"] = "pass"
        except AssertionError as exc:
            results["checks"]["step5_timeline_persists"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s5_timeline", snapshot)
            print(json.dumps(results, indent=2))
            return results

        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == timeline_view_id:
            results["checks"]["step5_api_unchanged"] = "pass"
        else:
            results["checks"]["step5_api_unchanged"] = (
                f"fail: expected {timeline_view_id}, got {tbl.get('default_view')}"
            )

        _snap(page, "vd_06_final", snapshot)

        failed = [k for k, v in results["checks"].items() if str(v).startswith("fail")]
        results["passed"] = len(failed) == 0
        if failed:
            results["failed_checks"] = failed

    finally:
        try:
            browser.close()
        except Exception:
            pass
        pw.stop()
        if ws_id is not None and token is not None:
            _teardown(token, ws_id)

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    snapshot_mode = "--snapshot" in sys.argv
    result = run(snapshot=snapshot_mode)
    sys.exit(0 if result.get("passed") else 1)
