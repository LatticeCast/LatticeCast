#!/usr/bin/env python3
"""
E2E test: e2e_test_view_kanban_groupby — group_by change persists across navigation.

Topic: Kanban view group_by selector — UI change updates DB config; round-trip
navigation proves the setting is durable, not in-memory only.

Flow:
  setup:  bootstrap test user → API create PM table (Kanban + Status/Priority/Type selects)
  step 1: navigate to PM table → assert Kanban renders → API verify initial group_by
  step 2: select a different group_by column → assert UI shows new column →
          API verify config.group_by updated
  step 3: navigate away (workspace root) and back → assert group_by still active →
          API verify persisted (not just in-memory)
  teardown: DELETE test table via API

Run:
  docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_groupby.py
  docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_groupby.py --snapshot
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).parent))
from snapshot_decorator import set_snapshot_enabled, snapshot as step_snapshot
import bootstrap as _bootstrap

BASE_URL = os.environ.get("BASE_URL", "http://localhost:13491")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://dba_user:dba_pws@localhost:15432/db"
)
BROWSER_WS = os.environ.get("BROWSER_WS", "")
SCREENSHOT_DIR = "/output"

_SUFFIX = int(time.time()) % 100000
TABLE_ID = f"kgb-{_SUFFIX}"


# ── API helpers ───────────────────────────────────────────────────────────────

def _api(method: str, path: str, token: str, **kwargs):
    r = requests.request(
        method,
        f"{BASE_URL}/api/v1{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        **kwargs,
    )
    if not r.ok:
        raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
    return r.json()


def _get_workspaces(token: str) -> list:
    return _api("GET", "/workspaces", token)


def _create_pm_table(token: str, workspace_name: str, table_id: str) -> dict:
    return _api(
        "POST",
        "/tables/template/pm",
        token,
        json={"table_id": table_id, "workspace_name": workspace_name},
    )


def _get_table(token: str, table_id: str) -> dict:
    return _api("GET", f"/tables/{table_id}", token)


def _get_view(token: str, table_id: str, view_id: int) -> dict:
    return _api("GET", f"/tables/{table_id}/views/{view_id}", token)


def _delete_table(token: str, table_id: str) -> None:
    r = requests.delete(
        f"{BASE_URL}/api/v1/tables/{table_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code not in (200, 204, 404):
        print(f"[warn] DELETE {table_id} → {r.status_code}", file=sys.stderr)


# ── browser auth helper ───────────────────────────────────────────────────────

def _login_info(token: str, user_name: str) -> dict:
    return {
        "provider": "none",
        "accessToken": token,
        "userInfo": {"sub": token, "email": f"{user_name}@local", "name": user_name},
        "role": "user",
    }


def _snap(page, name: str) -> None:
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


# ── steps ─────────────────────────────────────────────────────────────────────

def step_navigate_to_kanban(page, workspace_name: str, table_id: str, token: str, snap: bool) -> dict:
    """Navigate to the PM table and confirm Kanban view loaded. Returns fresh schema."""
    print(f"[1] Navigate to /{workspace_name}/{table_id}", file=sys.stderr)
    try:
        page.goto(
            f"{BASE_URL}/{workspace_name}/{table_id}",
            wait_until="networkidle",
            timeout=20000,
        )
    except PlaywrightTimeout:
        pass

    if "/login" in page.url:
        raise AssertionError(f"Auth failed — redirected to {page.url}")

    # Kanban is loaded when the group-by selector is visible (it lives in the
    # Kanban toolbar and is absent in Table / Timeline views).
    try:
        page.wait_for_selector(
            '[data-testid="group-by-selector"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        if snap:
            _snap(page, "kgb_01_FAIL_kanban_not_loaded")
        raise AssertionError("Kanban group-by selector not visible — Kanban may not have loaded")

    if snap:
        _snap(page, "kgb_01_kanban_loaded")

    # API pillar: confirm kanban view exists and has group_by set.
    schema = _get_table(token, table_id)
    kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
    assert kanban_views, (
        f"No kanban view in table schema. view types: "
        f"{[v.get('type') for v in schema.get('views', [])]}"
    )
    kanban_view = kanban_views[0]
    initial_group_by = kanban_view.get("config", {}).get("group_by")
    assert initial_group_by, f"PM kanban view has no initial group_by: {kanban_view['config']}"

    print(
        f"    view_id={kanban_view['view_id']}  initial group_by={initial_group_by!r}",
        file=sys.stderr,
    )
    return schema


def step_change_group_by(page, token: str, table_id: str, schema: dict, snap: bool) -> str:
    """Switch group_by to a different select column; verify both UI + API update."""
    print("[2] Change group_by selector", file=sys.stderr)

    kanban_view = next(v for v in schema["views"] if v["type"] == "kanban")
    view_id: int = kanban_view["view_id"]
    current_group_by: str = kanban_view["config"]["group_by"]

    select_cols = [
        c
        for c in schema.get("columns", [])
        if c.get("type") == "select" and c.get("column_id") != current_group_by
    ]
    assert select_cols, (
        "Need at least 2 select columns to test group_by switch. "
        f"columns: {[(c.get('name'), c.get('type')) for c in schema.get('columns', [])]}"
    )
    new_col = select_cols[0]
    new_col_id: str = new_col["column_id"]
    new_col_name: str = new_col.get("name", new_col_id)
    print(
        f"    switching from {current_group_by!r} → {new_col_id!r} ({new_col_name!r})",
        file=sys.stderr,
    )

    # UI: select the new column in the group-by dropdown.
    selector = page.locator('[data-testid="group-by-selector"]')
    selector.wait_for(state="visible", timeout=8000)
    selector.select_option(value=new_col_id)

    # Give the frontend time to debounce + PUT the view update.
    page.wait_for_timeout(1500)

    if snap:
        _snap(page, "kgb_02_after_group_by_change")

    # UI pillar: selector value reflects the change.
    ui_val = selector.evaluate("el => el.value")
    assert ui_val == new_col_id, (
        f"UI: group-by selector shows {ui_val!r}, expected {new_col_id!r}"
    )

    # API pillar: config.group_by persisted to the backend.
    view = _get_view(token, table_id, view_id)
    api_val = view.get("config", {}).get("group_by")
    assert api_val == new_col_id, (
        f"API: config.group_by={api_val!r}, expected {new_col_id!r}"
    )

    print(f"    group_by updated — UI + API both show {new_col_id!r}", file=sys.stderr)
    return new_col_id


def step_verify_persistence(
    page,
    workspace_name: str,
    table_id: str,
    token: str,
    expected_group_by: str,
    kanban_view_id: int,
    snap: bool,
) -> None:
    """Navigate away then back; confirm group_by survived the round-trip."""
    print("[3] Navigate away and back — verify persistence", file=sys.stderr)

    # Navigate away to the workspace root.
    try:
        page.goto(
            f"{BASE_URL}/{workspace_name}",
            wait_until="networkidle",
            timeout=12000,
        )
    except PlaywrightTimeout:
        pass

    # Navigate back to the Kanban table.
    try:
        page.goto(
            f"{BASE_URL}/{workspace_name}/{table_id}",
            wait_until="networkidle",
            timeout=20000,
        )
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector(
            '[data-testid="group-by-selector"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        if snap:
            _snap(page, "kgb_03_FAIL_selector_after_nav")
        raise AssertionError("group-by selector not visible after round-trip navigation")

    page.wait_for_timeout(500)

    if snap:
        _snap(page, "kgb_03_after_round_trip")

    # UI pillar: selector still shows the updated column.
    selector = page.locator('[data-testid="group-by-selector"]')
    ui_val = selector.evaluate("el => el.value")
    assert ui_val == expected_group_by, (
        f"UI after round-trip: group-by shows {ui_val!r}, expected {expected_group_by!r}"
    )

    # API pillar: config.group_by still equals the updated column.
    view = _get_view(token, table_id, kanban_view_id)
    api_val = view.get("config", {}).get("group_by")
    assert api_val == expected_group_by, (
        f"API after round-trip: config.group_by={api_val!r}, expected {expected_group_by!r}"
    )

    print(f"    persistence confirmed — group_by={expected_group_by!r}", file=sys.stderr)


# ── main ──────────────────────────────────────────────────────────────────────

def run(with_snapshot: bool) -> int:
    if with_snapshot:
        set_snapshot_enabled(True)

    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")

    print("[bootstrap] creating test fixtures …", file=sys.stderr)
    try:
        fixtures = _bootstrap.run(suffix=today, base=BASE_URL, dsn=DATABASE_URL)
    except Exception as exc:
        print(f"[bootstrap] FAILED: {exc}", file=sys.stderr)
        return 1

    user = fixtures["user"]
    token: str = user["token"]
    workspace_uuid: str = user["workspace_id"]

    # Resolve workspace_name (used in URL navigation).
    workspaces = _get_workspaces(token)
    ws = next((w for w in workspaces if w["workspace_id"] == workspace_uuid), None)
    if ws is None:
        print(f"[ERROR] workspace {workspace_uuid} not found in /workspaces", file=sys.stderr)
        return 1
    workspace_name: str = ws["workspace_name"]
    print(
        f"[bootstrap] user={user['user_name']}  workspace_name={workspace_name}",
        file=sys.stderr,
    )

    # API: create PM table (idempotent — use existing if already present).
    print(f"[setup] create PM table '{TABLE_ID}' …", file=sys.stderr)
    try:
        schema = _create_pm_table(token, workspace_name, TABLE_ID)
    except RuntimeError as exc:
        if "409" in str(exc):
            schema = _get_table(token, TABLE_ID)
        else:
            print(f"[ERROR] PM table create: {exc}", file=sys.stderr)
            return 1

    kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
    if not kanban_views:
        print("[ERROR] PM template produced no kanban view", file=sys.stderr)
        _delete_table(token, TABLE_ID)
        return 1
    kanban_view_id: int = kanban_views[0]["view_id"]

    # Browser session.
    info = _login_info(token, user["user_name"])

    if BROWSER_WS:
        pw = sync_playwright().start()
        browser = pw.chromium.connect(BROWSER_WS)
        using_remote = True
    else:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        using_remote = False

    failed = False
    try:
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(info)}));"
        )
        page = ctx.new_page()

        schema = step_navigate_to_kanban(page, workspace_name, TABLE_ID, token, with_snapshot)
        new_group_by = step_change_group_by(page, token, TABLE_ID, schema, with_snapshot)
        step_verify_persistence(
            page,
            workspace_name,
            TABLE_ID,
            token,
            new_group_by,
            kanban_view_id,
            with_snapshot,
        )

    except AssertionError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        failed = True
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(f"[ERROR] {exc}", file=sys.stderr)
        failed = True
    finally:
        try:
            ctx.close()
        except Exception:
            pass
        if not using_remote:
            try:
                browser.close()
            except Exception:
                pass
        pw.stop()

    # Teardown: remove the test table regardless of pass/fail.
    print(f"[teardown] DELETE table '{TABLE_ID}' …", file=sys.stderr)
    _delete_table(token, TABLE_ID)

    if not failed:
        print("[PASS] all kanban group_by steps passed", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="E2E: Kanban group_by persistence")
    ap.add_argument("--snapshot", action="store_true", help="save per-step screenshots")
    return run(with_snapshot=ap.parse_args().snapshot)


if __name__ == "__main__":
    sys.exit(main())
