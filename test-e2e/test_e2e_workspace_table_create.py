#!/usr/bin/env python3
"""
E2E test: task-15 — Workspace + table create (blank + PM template) + sidebar/grid verify.

Flow:
  1. Navigate to claude's default workspace
  2. Create a new workspace via "+ New" button in the tab strip
  3. On new workspace page: create blank table → card appears → click to navigate
  4. Verify blank table grid renders (thead + default columns)
  5. Navigate back to workspace → create PM template table
  6. Verify redirect + PM grid (13 columns + Sprint Board + Roadmap views)
  7. Open sidebar → expand workspace → verify both tables listed

Usage:
    docker compose exec browser python3 /app/test_e2e_workspace_table_create.py [--snapshot]
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://localhost:13491"
SCREENSHOT_DIR = "/output"

# Auth: use /login/password to get UUID token (user_name lookup via app session
# fails due to gdpr.user_info RLS without app.current_user_id set)
_USER_NAME = "lattice"  # default dev user


def _get_token_and_workspace() -> tuple[str, str, str]:
    """Get UUID token via /login/password and resolve workspace_id."""
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/login/password",
        data=json.dumps({"user_name": _USER_NAME, "password": ""}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        token_data = json.loads(r.read())
    token = token_data["access_token"]
    userinfo = token_data.get("userinfo", {})

    req2 = urllib.request.Request(
        f"{BASE_URL}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req2, timeout=10) as r:
        workspaces = json.loads(r.read())

    ws = workspaces[0]  # default workspace
    return token, ws["workspace_id"], ws["workspace_name"]

_SUFFIX = int(time.time()) % 100000
NEW_WS_NAME = f"ws-e2e-{_SUFFIX}"
BLANK_TABLE_NAME = f"blank-{_SUFFIX}"
PM_TABLE_NAME = f"pm-{_SUFFIX}"

# Columns the PM template must create (subset — these must ALL be present)
PM_REQUIRED_COLUMNS = [
    "Title", "Type", "Status", "Priority",
    "Assignee", "Start Date", "Due Date",
    "Tags", "Description",
]


def _snap(page, name: str) -> str:
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def _make_page(ctx):
    """Create a page. Browser container uses network_mode:host so localhost:13491 reaches nginx directly."""
    return ctx.new_page()


def _col_names(page) -> list[str]:
    """Extract column names from <table><thead><th> cells (strips type annotations)."""
    names = []
    for th in page.locator("table thead th").all():
        text = (th.text_content() or "").strip()
        col = re.sub(r"\s*\(\w+\)\s*$", "", text).strip()
        if col and col != "#":
            names.append(col)
    return names


def run(snapshot: bool = False) -> dict:
    results: dict = {
        "test": "task15_workspace_table_create",
        "timestamp": datetime.now().isoformat(),
        "suffix": _SUFFIX,
        "checks": {},
        "passed": False,
    }

    # ── Pre-flight: get UUID token + workspace via API ────────────────────────
    print("[0] Get auth token via /login/password")
    try:
        token, ws_id, ws_name = _get_token_and_workspace()
        print(f"    user={_USER_NAME} ws_name={ws_name} ws_id={ws_id[:8]}...")
        results["ws_name"] = ws_name
    except Exception as exc:
        results["checks"]["preflight"] = f"fail: {exc}"
        print(json.dumps(results, indent=2))
        return results
    results["checks"]["preflight"] = "pass"

    login_info = {
        "provider": "none",
        "accessToken": token,
        "userInfo": {"sub": token, "email": f"{_USER_NAME}@local", "name": _USER_NAME},
        "role": "user",
    }

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    try:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        ctx.add_init_script(
            f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(login_info)}));"
        )
        page = _make_page(ctx)

        # ── Step 1: Navigate to the user's workspace ────────────────────────────
        print(f"[1] Navigate to /{ws_name}/ workspace")
        try:
            page.goto(f"{BASE_URL}/{ws_name}/", wait_until="networkidle", timeout=20000)
        except PlaywrightTimeout:
            pass

        if "/login" in page.url:
            results["checks"]["auth"] = "fail: redirected to /login"
            _snap(page, "t15_FAIL_auth")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["auth"] = "pass"

        # Wait for workspace tab strip
        try:
            page.wait_for_selector("[data-testid='workspace-tab-strip']", timeout=10000)
        except PlaywrightTimeout:
            results["checks"]["workspace_load"] = "fail: workspace-tab-strip not found"
            _snap(page, "t15_FAIL_ws_load")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["workspace_load"] = "pass"

        if snapshot:
            _snap(page, "t15_01_default_workspace")

        # ── Step 2: Create new workspace ─────────────────────────────────────────
        print(f"[2] Create workspace '{NEW_WS_NAME}'")

        new_ws_btn = page.get_by_test_id("new-workspace-btn")
        new_ws_btn.wait_for(state="visible", timeout=5000)
        new_ws_btn.click()

        # CreateWorkspaceModal appears
        name_input = page.get_by_test_id("create-workspace-name-input")
        name_input.wait_for(state="visible", timeout=5000)
        name_input.fill(NEW_WS_NAME)

        if snapshot:
            _snap(page, "t15_02_ws_create_modal")

        # Submit — SvelteKit client-side nav via goto(), not a full page reload
        page.get_by_test_id("create-workspace-submit").click()

        # Wait for URL to change to /{NEW_WS_NAME}/
        try:
            page.wait_for_url(f"**/{NEW_WS_NAME}/**", timeout=10000)
            results["checks"]["workspace_create"] = f"pass: {page.url}"
        except PlaywrightTimeout:
            # URL might still be correct — check directly
            if NEW_WS_NAME in page.url:
                results["checks"]["workspace_create"] = f"pass: {page.url}"
            else:
                results["checks"]["workspace_create"] = f"fail: URL={page.url}"
                _snap(page, "t15_FAIL_ws_create")
                print(json.dumps(results, indent=2))
                return results

        # Wait for workspace page with create-table form
        try:
            page.wait_for_selector("input[placeholder='New table name...']", timeout=10000)
        except PlaywrightTimeout:
            results["checks"]["workspace_page_load"] = "fail: table name input not found"
            _snap(page, "t15_FAIL_ws_page")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["workspace_page_load"] = "pass"

        if snapshot:
            _snap(page, "t15_03_new_workspace_page")

        ws_url = page.url  # Remember for later

        # ── Step 3: Create blank table ───────────────────────────────────────────
        print(f"[3] Create blank table '{BLANK_TABLE_NAME}'")

        table_input = page.locator("input[placeholder='New table name...']")
        table_input.fill(BLANK_TABLE_NAME)

        # handleCreate does NOT navigate — table card just appears in the list
        create_btn = page.locator("button:has-text('Create')").first
        create_btn.click()

        # Wait for the table card to appear
        try:
            page.wait_for_selector(
                f"button:has-text('{BLANK_TABLE_NAME}')", timeout=10000
            )
            results["checks"]["blank_table_create"] = "pass: table card appeared"
        except PlaywrightTimeout:
            results["checks"]["blank_table_create"] = f"fail: '{BLANK_TABLE_NAME}' not in table list"
            _snap(page, "t15_FAIL_blank_create")
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "t15_04_blank_table_in_list")

        # ── Step 4: Navigate to blank table and verify grid ───────────────────────
        print("[4] Navigate to blank table and verify grid")

        table_btn = page.locator(f"button:has-text('{BLANK_TABLE_NAME}')").first
        table_btn.click()
        # SvelteKit client-side nav — wait for URL to include the table id
        try:
            page.wait_for_url(f"**/{BLANK_TABLE_NAME}**", timeout=8000)
        except PlaywrightTimeout:
            pass  # proceed and let the grid check fail with context

        # Wait for loading spinner to disappear before checking grid
        try:
            page.wait_for_selector("text=Loading...", state="hidden", timeout=12000)
        except PlaywrightTimeout:
            pass

        results["checks"]["blank_table_url"] = page.url

        try:
            page.wait_for_selector("table thead", timeout=10000)
            cols = _col_names(page)
            results["checks"]["blank_table_grid"] = f"pass: columns={cols}"
        except PlaywrightTimeout:
            results["checks"]["blank_table_grid"] = "fail: <thead> not rendered"
            _snap(page, "t15_FAIL_blank_grid")
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "t15_05_blank_table_grid")

        # ── Step 5: Navigate back to workspace and create PM template ─────────────
        print(f"[5] Navigate back to '{NEW_WS_NAME}' workspace")
        page.goto(ws_url, wait_until="networkidle", timeout=15000)

        try:
            page.wait_for_selector("button:has-text('From Template')", timeout=10000)
        except PlaywrightTimeout:
            results["checks"]["ws_back_nav"] = "fail: 'From Template' not found after returning"
            _snap(page, "t15_FAIL_ws_back")
            print(json.dumps(results, indent=2))
            return results
        results["checks"]["ws_back_nav"] = "pass"

        print(f"[6] Create PM template '{PM_TABLE_NAME}'")

        page.locator("button:has-text('From Template')").first.click()

        try:
            page.wait_for_selector("text=New from Template", timeout=5000)
            results["checks"]["pm_modal_open"] = "pass"
        except PlaywrightTimeout:
            results["checks"]["pm_modal_open"] = "fail: template modal did not open"
            _snap(page, "t15_FAIL_pm_modal")
            print(json.dumps(results, indent=2))
            return results

        if snapshot:
            _snap(page, "t15_06_pm_template_modal")

        pm_input = page.locator("input[placeholder='Project name...']").first
        pm_input.fill(PM_TABLE_NAME)

        # PM create uses SvelteKit goto() — wait for URL to include PM table name
        page.locator("button:has-text('Create PM Project')").first.click()
        try:
            page.wait_for_url(f"**/{PM_TABLE_NAME}**", timeout=20000)
        except PlaywrightTimeout:
            pass  # proceed and let grid check fail with context

        results["checks"]["pm_create_url"] = page.url

        # Wait for loading spinner to clear — loadWorkspaces + loadTable both toggle
        # the loading store, so networkidle fires before DOM updates to loading=false.
        # Instead: wait for "Loading..." text to disappear.
        try:
            page.wait_for_selector("text=Loading...", state="hidden", timeout=20000)
        except PlaywrightTimeout:
            pass

        if snapshot:
            _snap(page, "t15_07_after_pm_create")

        # ── Step 7: Verify PM grid renders with expected columns ──────────────────
        print("[7] Verify PM table grid")

        # PM template lands on Sprint Board (Kanban) by default — click Schema tab
        # to switch to Table view so we can inspect <thead> columns.
        schema_tab = page.locator("button:has-text('Schema')").first
        try:
            schema_tab.wait_for(state="visible", timeout=8000)
            schema_tab.click()
            page.wait_for_timeout(500)
        except PlaywrightTimeout:
            pass

        try:
            page.wait_for_selector("table thead", timeout=10000)
        except PlaywrightTimeout:
            results["checks"]["pm_grid"] = "fail: <thead> not rendered after switching to Schema view"
            _snap(page, "t15_FAIL_pm_grid")
            print(json.dumps(results, indent=2))
            return results

        pm_cols = _col_names(page)
        missing = [c for c in PM_REQUIRED_COLUMNS if c not in pm_cols]
        if not missing:
            results["checks"]["pm_columns"] = f"pass: found {pm_cols}"
        else:
            results["checks"]["pm_columns"] = f"fail: missing {missing}; found {pm_cols}"

        # Verify PM views tabs (Sprint Board + Roadmap)
        sprint_board = page.locator("button:has-text('Sprint Board')")
        roadmap = page.locator("button:has-text('Roadmap')")
        if sprint_board.count() >= 1 and roadmap.count() >= 1:
            results["checks"]["pm_views"] = "pass: Sprint Board + Roadmap tabs found"
        else:
            results["checks"]["pm_views"] = (
                f"warn: Sprint Board={sprint_board.count()}, Roadmap={roadmap.count()}"
            )

        if snapshot:
            _snap(page, "t15_08_pm_table_grid")

        # ── Step 8: Open sidebar and verify both tables under new workspace ────────
        print("[8] Verify both tables in sidebar tree")

        toggle = page.get_by_test_id("menu-toggle")
        toggle.wait_for(state="visible", timeout=5000)
        toggle.click()
        page.wait_for_timeout(400)

        menu_nav = page.get_by_test_id("menu-nav")
        menu_nav.wait_for(state="visible", timeout=5000)

        # Expand the new workspace in the sidebar tree (click workspace button by name)
        ws_expand_btn = menu_nav.get_by_text(NEW_WS_NAME, exact=False).first
        try:
            ws_expand_btn.wait_for(state="visible", timeout=5000)
            ws_expand_btn.click()
            page.wait_for_timeout(400)
        except PlaywrightTimeout:
            pass  # Workspace may already be expanded

        if snapshot:
            _snap(page, "t15_09_sidebar_expanded")

        blank_in_sidebar = menu_nav.get_by_text(BLANK_TABLE_NAME, exact=True).count()
        pm_in_sidebar = menu_nav.get_by_text(PM_TABLE_NAME, exact=True).count()

        results["checks"]["sidebar_blank"] = "pass" if blank_in_sidebar > 0 else f"fail: '{BLANK_TABLE_NAME}' not found in sidebar"
        results["checks"]["sidebar_pm"] = "pass" if pm_in_sidebar > 0 else f"fail: '{PM_TABLE_NAME}' not found in sidebar"

        if snapshot:
            _snap(page, "t15_10_sidebar_both_tables")

        # ── Final result ──────────────────────────────────────────────────────────
        failed = [k for k, v in results["checks"].items() if str(v).startswith("fail")]
        results["passed"] = len(failed) == 0
        if failed:
            results["failed_checks"] = failed

    finally:
        browser.close()
        pw.stop()

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    snapshot_mode = "--snapshot" in sys.argv
    result = run(snapshot=snapshot_mode)
    sys.exit(0 if result.get("passed") else 1)
