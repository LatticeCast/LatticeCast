#!/usr/bin/env python3
"""
E2E test: task-56 — CRM template structure (8 columns, 2 views).

Verifies:
  1. POST /api/v1/tables/template/crm → 8 columns with correct names+types
  2. Response includes 2 views: Pipeline (kanban) + Sales Dashboard (dashboard)
  3. Pipeline config: group_by=Stage, card_fields=[Title, Value, Owner]
  4. Sales Dashboard config: type=dashboard, 5 layout blocks, 5 block defs
  5. UI: Schema tab renders all 8 column names in <thead>
  6. UI: Pipeline + Sales Dashboard view tabs visible

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_template_crm.py [--snapshot]
"""

import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from e2e_base import BASE, BROWSER_WS, api, connect_browser, fatal, login, seed_login_info

USER = "lattice"
SUFFIX = int(time.time()) % 100000
WS_NAME = f"ws-crm-tpl-{SUFFIX}"
TABLE_NAME = f"crm-tpl-{SUFFIX}"

CRM_COLUMNS = [
    ("Title", "text"),
    ("Doc", "doc"),
    ("Stage", "select"),
    ("Value", "number"),
    ("Owner", "text"),
    ("Close Date", "date"),
    ("Tags", "tags"),
    ("Description", "text"),
]

STAGE_CHOICES = ["lead", "qualified", "proposal", "won", "lost"]


def main():
    snapshot = "--snapshot" in sys.argv

    print("[0] Login + create workspace")
    token = login(USER)

    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code not in (200, 201):
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]

    try:
        _run_test(token, ws_id, snapshot)
    finally:
        api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        print("[cleanup] workspace deleted")


def _run_test(token: str, ws_id: str, snapshot: bool):
    # ── Step 1: Create CRM template via API ──────────────────────────────────
    print("[1] POST /api/v1/tables/template/crm")
    r = api(
        "POST",
        "/api/v1/tables/template/crm",
        token,
        json={"table_id": TABLE_NAME, "workspace_id": ws_id},
    )
    if r.status_code not in (200, 201):
        fatal(f"create CRM template: {r.status_code} {r.text[:300]}")

    data = r.json()
    columns = data.get("columns", [])
    views = data.get("views", [])

    # ── Step 2: Verify columns (API pillar) ──────────────────────────────────
    print(f"[2] Verify columns: got {len(columns)}")

    col_map = {c["name"]: c for c in columns}

    expected_names = [name for name, _ in CRM_COLUMNS]
    missing = [n for n in expected_names if n not in col_map]
    if missing:
        fatal(f"missing columns: {missing}; got {list(col_map.keys())}")

    assert len(columns) == len(CRM_COLUMNS), (
        f"expected {len(CRM_COLUMNS)} columns, got {len(columns)}: "
        f"{[c['name'] for c in columns]}"
    )

    for name, expected_type in CRM_COLUMNS:
        actual_type = col_map[name]["type"]
        assert actual_type == expected_type, (
            f"column '{name}': expected type '{expected_type}', got '{actual_type}'"
        )

    stage_opts = col_map["Stage"].get("options", {})
    stage_values = [ch["value"] for ch in stage_opts.get("choices", [])]
    assert stage_values == STAGE_CHOICES, (
        f"Stage choices: expected {STAGE_CHOICES}, got {stage_values}"
    )

    print("    columns OK")

    # ── Step 3: Verify views (API pillar) ─────────────────────────────────────
    print(f"[3] Verify views: got {len(views)}")
    assert len(views) == 2, f"expected 2 views, got {len(views)}: {views}"

    view_by_name = {v["name"]: v for v in views}
    assert "Pipeline" in view_by_name, f"missing 'Pipeline'; got {list(view_by_name.keys())}"
    assert "Sales Dashboard" in view_by_name, (
        f"missing 'Sales Dashboard'; got {list(view_by_name.keys())}"
    )

    pipeline = view_by_name["Pipeline"]
    assert pipeline["type"] == "kanban", (
        f"Pipeline type: expected 'kanban', got '{pipeline['type']}'"
    )

    pipeline_cfg = pipeline.get("config", {})
    stage_col_id = col_map["Stage"]["column_id"]
    assert pipeline_cfg.get("group_by") == stage_col_id, (
        f"Pipeline group_by: expected Stage col_id '{stage_col_id}', "
        f"got '{pipeline_cfg.get('group_by')}'"
    )

    expected_card_fields = [
        col_map["Title"]["column_id"],
        col_map["Value"]["column_id"],
        col_map["Owner"]["column_id"],
    ]
    assert pipeline_cfg.get("card_fields") == expected_card_fields, (
        f"Pipeline card_fields mismatch: expected {expected_card_fields}, "
        f"got {pipeline_cfg.get('card_fields')}"
    )

    dashboard = view_by_name["Sales Dashboard"]
    assert dashboard["type"] == "dashboard", (
        f"Sales Dashboard type: expected 'dashboard', got '{dashboard['type']}'"
    )

    dash_cfg = dashboard.get("config", {})
    layout = dash_cfg.get("layout", [])
    assert len(layout) == 5, f"Sales Dashboard layout: expected 5 widgets, got {len(layout)}"

    layout_ids = {item["id"] for item in layout}
    expected_layout_ids = {"pipeline_value", "by_stage", "by_owner", "won_value", "recent"}
    assert layout_ids == expected_layout_ids, (
        f"layout ids mismatch: expected {expected_layout_ids}, got {layout_ids}"
    )

    blocks = dash_cfg.get("blocks", {})
    assert set(blocks.keys()) == expected_layout_ids, (
        f"blocks keys mismatch: expected {expected_layout_ids}, got {set(blocks.keys())}"
    )

    assert blocks["pipeline_value"]["kind"] == "number"
    assert blocks["by_stage"]["kind"] == "chart"
    assert blocks["by_owner"]["kind"] == "chart"
    assert blocks["won_value"]["kind"] == "number"
    assert blocks["recent"]["kind"] == "list"

    default_view = data.get("default_view")
    assert default_view == pipeline["view_id"], (
        f"default_view: expected {pipeline['view_id']}, got {default_view}"
    )

    print("    views OK")

    # ── Step 4: UI verification ──────────────────────────────────────────────
    print("[4] UI: navigate to CRM table")
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, USER)

        page.goto(f"{BASE}/{WS_NAME}/{TABLE_NAME}", wait_until="networkidle")

        page.wait_for_selector("[data-testid='view-tab-Schema']", state="visible", timeout=10000)

        if snapshot:
            page.screenshot(path="/output/t56_01_crm_table_landing.png", full_page=True)

        # ── Step 5: verify view tabs exist ───────────────────────────────────
        print("[5] UI: verify view tabs")
        page.wait_for_selector(
            "[data-testid='view-tab-Pipeline']", state="visible", timeout=5000
        )
        page.wait_for_selector(
            "[data-testid='view-tab-Sales Dashboard']", state="visible", timeout=5000
        )
        print("    Pipeline + Sales Dashboard tabs visible")

        # ── Step 6: click Schema tab and verify column headers ───────────────
        print("[6] UI: click Schema tab, verify column headers")
        page.get_by_test_id("view-tab-Schema").click()
        page.wait_for_selector("table thead", state="visible", timeout=8000)

        if snapshot:
            page.screenshot(path="/output/t56_02_schema_view.png", full_page=True)

        th_elements = page.locator("table thead th").all()
        rendered_names = []
        for th in th_elements:
            text = " ".join((th.text_content() or "").split())
            col_name = re.sub(r"\s*\(\w+\)\s*$", "", text).strip()
            if col_name and col_name != "#":
                rendered_names.append(col_name)

        expected_names_set = set(expected_names)
        rendered_set = set(rendered_names)
        missing_in_ui = expected_names_set - rendered_set
        if missing_in_ui:
            fatal(f"columns missing from UI thead: {missing_in_ui}; rendered: {rendered_names}")

        print(f"    all {len(expected_names)} columns rendered in thead")

        if snapshot:
            page.screenshot(path="/output/t56_03_columns_verified.png", full_page=True)

        browser.close()

    print("PASS: e2e_test_template_crm")


if __name__ == "__main__":
    main()
