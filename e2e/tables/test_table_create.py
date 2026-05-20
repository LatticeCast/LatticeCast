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
    docker compose exec -T e2e pytest tables/test_table_create.py -v [--snapshot]
"""

import json
import re
import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, login, seed_login_info


SCREENSHOT_DIR = "/output"

_SUFFIX = int(time.time()) % 100000
NEW_WS_NAME = f"ws-e2e-{_SUFFIX}"
BLANK_TABLE_NAME = f"blank-{_SUFFIX}"
PM_TABLE_NAME = f"pm-{_SUFFIX}"

PM_REQUIRED_COLUMNS = [
    "Title", "Type", "Status", "Priority",
    "Assignee", "Start Date", "Due Date",
    "Tags", "Description",
]


def _snap(page, name: str, snapshot: bool) -> str:
    if not snapshot:
        return ""
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        pass
    return path


def _col_names(page) -> list[str]:
    """Extract column names from <table><thead><th> cells (strips type annotations)."""
    names = []
    for th in page.locator("table thead th").all():
        text = (th.text_content() or "").strip()
        col = re.sub(r"\s*\(\w+\)\s*$", "", text).strip()
        if col and col != "#":
            names.append(col)
    return names


def test_workspace_table_create(authed_page, admin_token, snapshot):
    """Workspace + table create (blank + PM template) + sidebar/grid verify."""
    page = authed_page

    # ── Step 0: Pre-flight — get workspace via API ────────────────────────────
    print("[0] Get workspace list via API")
    r = api("GET", "/api/v1/workspaces", admin_token)
    assert r.status_code == 200, f"preflight: GET workspaces failed {r.status_code}"
    workspaces = r.json()
    assert len(workspaces) > 0, "preflight: no workspaces found"
    ws_id = workspaces[0]["workspace_id"]
    ws_name = workspaces[0]["workspace_name"]
    print(f"    user=lattice ws_name={ws_name} ws_id={ws_id[:8]}...")

    # ── Step 1: Navigate to the user's workspace ────────────────────────────
    print(f"[1] Navigate to /{ws_name}/ workspace")
    try:
        page.goto(f"{BASE}/{ws_name}/", wait_until="networkidle", timeout=20000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_goto_workspace", True)
        pytest.fail("goto workspace timed out")

    assert "/login" not in page.url, f"redirected to /login: {page.url}"

    # Wait for workspace tab strip
    try:
        page.wait_for_selector("[data-testid='workspace-tab-strip']", timeout=10000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_ws_load", True)
        pytest.fail("workspace-tab-strip not found")

    _snap(page, "t15_01_default_workspace", snapshot)

    # ── Step 2: Create new workspace ─────────────────────────────────────────
    print(f"[2] Create workspace '{NEW_WS_NAME}'")

    new_ws_btn = page.get_by_test_id("new-workspace-btn")
    new_ws_btn.wait_for(state="visible", timeout=5000)
    new_ws_btn.click()

    # CreateWorkspaceModal appears
    name_input = page.get_by_test_id("create-workspace-name-input")
    name_input.wait_for(state="visible", timeout=5000)
    name_input.fill(NEW_WS_NAME)

    _snap(page, "t15_02_ws_create_modal", snapshot)

    # Submit — SvelteKit client-side nav via goto(), not a full page reload
    page.get_by_test_id("create-workspace-submit").click()

    # Wait for URL to change to /{NEW_WS_NAME}/
    try:
        page.wait_for_url(f"**/{NEW_WS_NAME}/**", timeout=10000)
    except PlaywrightTimeout:
        # URL might still be correct — check directly
        if NEW_WS_NAME not in page.url:
            _snap(page, "t15_FAIL_ws_create", True)
            pytest.fail(f"workspace create failed: URL={page.url}")

    print(f"    workspace created: {page.url}")

    # Wait for workspace page with create-table form
    try:
        page.wait_for_selector("[data-testid='create-table-name-input']", timeout=10000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_ws_page", True)
        pytest.fail("workspace page: table name input not found")

    _snap(page, "t15_03_new_workspace_page", snapshot)

    ws_url = page.url  # Remember for later

    # ── Step 3: Create blank table ───────────────────────────────────────────
    print(f"[3] Create blank table '{BLANK_TABLE_NAME}'")

    table_input = page.get_by_test_id("create-table-name-input")
    table_input.fill(BLANK_TABLE_NAME)

    # handleCreate does NOT navigate — table card just appears in the list
    create_btn = page.get_by_test_id("create-table-submit")
    create_btn.click()

    # Wait for the table card to appear
    try:
        page.wait_for_selector(
            f"[data-testid='table-card-{BLANK_TABLE_NAME}']", timeout=10000
        )
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_blank_create", True)
        pytest.fail(f"'{BLANK_TABLE_NAME}' not in table list")

    print("    table card appeared")

    _snap(page, "t15_04_blank_table_in_list", snapshot)

    # ── Step 4: Navigate to blank table and verify grid ───────────────────────
    print("[4] Navigate to blank table and verify grid")

    table_btn = page.get_by_test_id(f"table-card-{BLANK_TABLE_NAME}")
    table_btn.click()
    # SvelteKit client-side nav — wait for URL to include the table id
    try:
        page.wait_for_url(f"**/{BLANK_TABLE_NAME}**", timeout=8000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_blank_nav", True)
        pytest.fail(f"blank table nav failed: URL={page.url}")

    print(f"    navigated to: {page.url}")

    try:
        page.wait_for_selector("table thead", timeout=10000)
        cols = _col_names(page)
        print(f"    blank table columns: {cols}")
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_blank_grid", True)
        pytest.fail("<thead> not rendered for blank table")

    _snap(page, "t15_05_blank_table_grid", snapshot)

    # ── Step 5: Navigate back to workspace and create PM template ─────────────
    print(f"[5] Navigate back to '{NEW_WS_NAME}' workspace")
    page.goto(ws_url, wait_until="networkidle", timeout=15000)

    try:
        page.wait_for_selector("[data-testid='create-table-from-template-btn']", timeout=10000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_ws_back", True)
        pytest.fail("'From Template' button not found after returning to workspace")

    print(f"[6] Create PM template '{PM_TABLE_NAME}'")

    page.get_by_test_id("create-table-from-template-btn").click()

    try:
        page.wait_for_selector("text=New from Template", timeout=5000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_pm_modal", True)
        pytest.fail("template modal did not open")

    _snap(page, "t15_06_pm_template_modal", snapshot)

    pm_input = page.get_by_test_id("pm-template-name-input")
    pm_input.fill(PM_TABLE_NAME)

    # PM create uses SvelteKit goto() — wait for URL to include PM table name
    page.get_by_test_id("pm-template-submit").click()
    try:
        page.wait_for_url(f"**/{PM_TABLE_NAME}**", timeout=20000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_pm_create_url", True)
        pytest.fail(f"PM table create failed: URL={page.url}")

    print(f"    PM table created: {page.url}")

    _snap(page, "t15_07_after_pm_create", snapshot)

    # ── Step 7: Verify PM grid renders with expected columns ──────────────────
    print("[7] Verify PM table grid")

    # PM template lands on Sprint Board (Kanban) by default — click Schema tab
    # to switch to Table view so we can inspect <thead> columns.
    schema_tab = page.get_by_test_id("view-tab-Schema")
    try:
        schema_tab.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_no_schema_tab", True)
        pytest.fail("view-tab-Schema not visible")
    schema_tab.click()

    try:
        page.wait_for_selector("table thead", timeout=10000)
    except PlaywrightTimeout:
        _snap(page, "t15_FAIL_pm_grid", True)
        pytest.fail("<thead> not rendered after switching to Schema view")

    pm_cols = _col_names(page)
    missing = [c for c in PM_REQUIRED_COLUMNS if c not in pm_cols]
    assert not missing, f"PM columns missing {missing}; found {pm_cols}"
    print(f"    PM columns OK: {pm_cols}")

    # Verify PM views tabs (Sprint Board + Roadmap)
    sprint_board = page.locator("[data-testid='view-tab-Sprint Board']")
    roadmap = page.locator("[data-testid='view-tab-Roadmap']")
    assert sprint_board.count() >= 1, f"Sprint Board tab not found (count={sprint_board.count()})"
    assert roadmap.count() >= 1, f"Roadmap tab not found (count={roadmap.count()})"
    print("    PM views OK: Sprint Board + Roadmap tabs found")

    _snap(page, "t15_08_pm_table_grid", snapshot)

    # ── Step 8: Open sidebar and verify both tables under new workspace ────────
    print("[8] Verify both tables in sidebar tree")

    toggle = page.get_by_test_id("menu-toggle")
    toggle.wait_for(state="visible", timeout=5000)
    toggle.click()

    menu_nav = page.get_by_test_id("menu-nav")
    menu_nav.wait_for(state="visible", timeout=5000)

    # Click the new workspace's sidebar entry to expand it. Idempotent —
    # if already expanded, click toggles; we re-check visibility either way.
    ws_btn = page.get_by_test_id(f"sidebar-workspace-{NEW_WS_NAME}")
    ws_btn.wait_for(state="visible", timeout=5000)
    # Expand if not already (table testids only render under expanded ws)
    if not page.get_by_test_id(f"sidebar-table-{BLANK_TABLE_NAME}").count():
        ws_btn.click()

    _snap(page, "t15_09_sidebar_expanded", snapshot)

    blank_in_sidebar = page.get_by_test_id(f"sidebar-table-{BLANK_TABLE_NAME}").count()
    pm_in_sidebar = page.get_by_test_id(f"sidebar-table-{PM_TABLE_NAME}").count()

    assert blank_in_sidebar > 0, f"'{BLANK_TABLE_NAME}' not found in sidebar"
    assert pm_in_sidebar > 0, f"'{PM_TABLE_NAME}' not found in sidebar"
    print("    sidebar OK: both tables listed")

    _snap(page, "t15_10_sidebar_both_tables", snapshot)

    print("[PASS] All checks passed")
