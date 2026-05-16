#!/usr/bin/env python3
"""
E2E test: last-clicked view sticks across navigation.

Topic: switching to a view sets it as the default so that navigating away
       and back (without ?view= in the URL) restores the same view.

Flow:
  Setup — login, create test table + Kanban view + Timeline view via API.
  Step 1 — load table page; verify Schema tab is active (default_view=null).
  Step 2 — click Kanban tab; wait for PATCH /schema; API + UI assert.
  Step 3 — navigate away (workspace); navigate back (no ?view=); assert Kanban still active.
  Step 4 — click Timeline tab; wait for PATCH /schema; API + UI assert.
  Step 5 — navigate away; navigate back; assert Timeline still active.
  Teardown — DELETE test table.

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

BASE_URL = os.environ.get("BASE_URL", "http://localhost:13491")
BROWSER_WS = os.environ.get("BROWSER_WS", "")
SCREENSHOT_DIR = "/output"

_USER_NAME = "lattice"
_SUFFIX = int(time.time()) % 100000
TABLE_ID = f"e2e-views-default-{_SUFFIX}"


# ── API helpers ──────────────────────────────────────────────────────────────


def _login(user_name: str) -> tuple[str, str, str]:
    """POST /login/password → (token, workspace_id, workspace_name)."""
    r = requests.post(
        f"{BASE_URL}/api/v1/login/password",
        json={"user_name": user_name, "password": ""},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed {r.status_code}: {r.text[:200]}")
    token = r.json()["access_token"]

    r2 = requests.get(
        f"{BASE_URL}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r2.status_code != 200:
        raise RuntimeError(f"list workspaces failed: {r2.text[:200]}")
    ws = r2.json()[0]
    return token, str(ws["workspace_id"]), ws["workspace_name"]


def _api(method: str, path: str, token: str, **kw) -> requests.Response:
    return getattr(requests, method)(
        f"{BASE_URL}/api/v1{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        **kw,
    )


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


# ── UI helpers ───────────────────────────────────────────────────────────────


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


def _wait_table_page(page, ws_name: str, table_id: str, timeout: int = 20000) -> None:
    """Navigate to the table page and wait for the ViewSwitcher to render."""
    page.goto(f"{BASE_URL}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=timeout)
    # Wait for the view switcher add button to appear (proves ViewSwitcher mounted)
    try:
        page.wait_for_selector('[data-testid="view-switcher-add-btn"]', timeout=timeout)
    except PlaywrightTimeout:
        raise AssertionError(f"ViewSwitcher did not render for table {table_id!r}")


# ── Main test ────────────────────────────────────────────────────────────────


def run(snapshot: bool = False) -> dict:
    results: dict = {
        "test": "e2e_test_views_default",
        "timestamp": datetime.now().isoformat(),
        "table_id": TABLE_ID,
        "checks": {},
        "passed": False,
    }

    # ── Pre-flight: login + create test table + two views ────────────────────
    print("[0] Pre-flight: login and create test table via API")
    try:
        token, ws_uuid, ws_name = _login(_USER_NAME)
        print(f"    user={_USER_NAME!r} ws={ws_name!r}")
    except Exception as exc:
        results["checks"]["login"] = f"fail: {exc}"
        print(json.dumps(results, indent=2))
        return results
    results["checks"]["login"] = "pass"

    # Create test table
    r = _api("post", "/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    if r.status_code != 201:
        results["checks"]["create_table"] = f"fail: {r.status_code} {r.text[:200]}"
        print(json.dumps(results, indent=2))
        return results
    results["checks"]["create_table"] = "pass"

    # Create Kanban view
    r = _api("post", f"/tables/{TABLE_ID}/views", token, json={"name": "Kanban", "type": "kanban"})
    if r.status_code != 201:
        results["checks"]["create_kanban"] = f"fail: {r.status_code} {r.text[:200]}"
        print(json.dumps(results, indent=2))
        return results
    schema = r.json()
    kanban_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Kanban")
    results["checks"]["create_kanban"] = f"pass: view_id={kanban_view_id}"

    # Create Timeline view
    r = _api("post", f"/tables/{TABLE_ID}/views", token, json={"name": "Timeline", "type": "timeline"})
    if r.status_code != 201:
        results["checks"]["create_timeline"] = f"fail: {r.status_code} {r.text[:200]}"
        print(json.dumps(results, indent=2))
        return results
    schema = r.json()
    timeline_view_id = next(v["view_id"] for v in schema.get("views", []) if v["name"] == "Timeline")
    results["checks"]["create_timeline"] = f"pass: view_id={timeline_view_id}"

    # Verify initial default_view is null (fresh table)
    tbl = _get_table(TABLE_ID, token)
    if tbl.get("default_view") is not None:
        results["checks"]["initial_default_null"] = f"warn: default_view={tbl['default_view']} (expected null)"
    else:
        results["checks"]["initial_default_null"] = "pass"

    login_info = {
        "provider": "none",
        "accessToken": token,
        "userInfo": {"sub": token, "email": f"{_USER_NAME}@local", "name": _USER_NAME},
        "role": "user",
    }

    # ── Browser session ──────────────────────────────────────────────────────
    pw = sync_playwright().start()
    browser = pw.chromium.connect(BROWSER_WS) if BROWSER_WS else pw.chromium.launch(headless=True)

    try:
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(login_info)}));"
        )
        page = ctx.new_page()

        # ── Step 1: Load table page; Schema tab active by default ────────────
        print("[1] Load table page; verify Schema tab active")
        try:
            _wait_table_page(page, ws_name, TABLE_ID)
        except AssertionError as exc:
            results["checks"]["step1_page_load"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s1_load", snapshot)
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "vd_01_initial_load", snapshot)

        # Schema is the implicit default when default_view=null
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
        except PlaywrightTimeout:
            results["checks"]["step2_patch_schema"] = "fail: PATCH /schema timed out after click"
            _snap(page, "vd_FAIL_s2_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results
        except AssertionError as exc:
            results["checks"]["step2_patch_schema"] = f"fail: {exc}"
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "vd_02_kanban_clicked", snapshot)

        # UI assert: Kanban tab active
        try:
            _assert_tab_active(page, "Kanban")
            _assert_tab_inactive(page, "Schema")
            results["checks"]["step2_ui_kanban_active"] = "pass"
        except AssertionError as exc:
            results["checks"]["step2_ui_kanban_active"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s2_ui", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # API assert: default_view == kanban_view_id
        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == kanban_view_id:
            results["checks"]["step2_api_default_view"] = f"pass: default_view={kanban_view_id}"
        else:
            results["checks"]["step2_api_default_view"] = (
                f"fail: expected default_view={kanban_view_id}, got {tbl.get('default_view')}"
            )
            print(json.dumps(results, indent=2))
            return results

        # ── Step 3: Navigate away; navigate back; verify Kanban restored ─────
        print("[3] Navigate away to workspace; navigate back; assert Kanban still active")

        page.goto(f"{BASE_URL}/{ws_name}", wait_until="domcontentloaded", timeout=15000)

        try:
            _wait_table_page(page, ws_name, TABLE_ID)
        except AssertionError as exc:
            results["checks"]["step3_page_reload"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s3_reload", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # Verify no ?view= param in URL (we navigated without it)
        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        if snapshot:
            _snap(page, "vd_03_back_after_kanban", snapshot)

        # UI assert: Kanban still active (restored from default_view)
        try:
            _wait_tab_active(page, "Kanban")
            _assert_tab_inactive(page, "Schema")
            results["checks"]["step3_kanban_persists"] = "pass"
        except AssertionError as exc:
            results["checks"]["step3_kanban_persists"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s3_kanban", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # API assert: default_view unchanged
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
        except PlaywrightTimeout:
            results["checks"]["step4_patch_schema"] = "fail: PATCH /schema timed out after click"
            _snap(page, "vd_FAIL_s4_patch", snapshot)
            print(json.dumps(results, indent=2))
            return results
        except AssertionError as exc:
            results["checks"]["step4_patch_schema"] = f"fail: {exc}"
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "vd_04_timeline_clicked", snapshot)

        # UI assert: Timeline tab active
        try:
            _assert_tab_active(page, "Timeline")
            _assert_tab_inactive(page, "Kanban")
            results["checks"]["step4_ui_timeline_active"] = "pass"
        except AssertionError as exc:
            results["checks"]["step4_ui_timeline_active"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s4_ui", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # API assert: default_view == timeline_view_id
        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == timeline_view_id:
            results["checks"]["step4_api_default_view"] = f"pass: default_view={timeline_view_id}"
        else:
            results["checks"]["step4_api_default_view"] = (
                f"fail: expected default_view={timeline_view_id}, got {tbl.get('default_view')}"
            )
            print(json.dumps(results, indent=2))
            return results

        # ── Step 5: Navigate away; navigate back; verify Timeline restored ────
        print("[5] Navigate away; navigate back; assert Timeline still active")

        page.goto(f"{BASE_URL}/{ws_name}", wait_until="domcontentloaded", timeout=15000)

        try:
            _wait_table_page(page, ws_name, TABLE_ID)
        except AssertionError as exc:
            results["checks"]["step5_page_reload"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s5_reload", snapshot)
            print(json.dumps(results, indent=2))
            return results

        assert "view=" not in page.url, f"URL unexpectedly contains ?view=: {page.url}"

        if snapshot:
            _snap(page, "vd_05_back_after_timeline", snapshot)

        # UI assert: Timeline still active
        try:
            _wait_tab_active(page, "Timeline")
            _assert_tab_inactive(page, "Kanban")
            results["checks"]["step5_timeline_persists"] = "pass"
        except AssertionError as exc:
            results["checks"]["step5_timeline_persists"] = f"fail: {exc}"
            _snap(page, "vd_FAIL_s5_timeline", snapshot)
            print(json.dumps(results, indent=2))
            return results

        # API assert: default_view unchanged
        tbl = _get_table(TABLE_ID, token)
        if tbl.get("default_view") == timeline_view_id:
            results["checks"]["step5_api_unchanged"] = "pass"
        else:
            results["checks"]["step5_api_unchanged"] = (
                f"fail: expected {timeline_view_id}, got {tbl.get('default_view')}"
            )

        if snapshot:
            _snap(page, "vd_06_final", snapshot)

        # ── Final result ─────────────────────────────────────────────────────
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

        # Teardown: delete test table
        print(f"[teardown] DELETE /tables/{TABLE_ID}")
        r = _api("delete", f"/tables/{TABLE_ID}", token)
        if r.status_code not in (200, 204):
            print(f"  warn: teardown delete returned {r.status_code}", file=sys.stderr)

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    snapshot_mode = "--snapshot" in sys.argv
    result = run(snapshot=snapshot_mode)
    sys.exit(0 if result.get("passed") else 1)
