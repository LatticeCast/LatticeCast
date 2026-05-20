"""
E2E test: task-55 — PM template structure (12 columns, 2 views).

Verifies:
  1. POST /api/v1/tables/template/pm → 12 columns with correct names+types
  2. Response includes 2 views: Sprint Board (kanban) + Roadmap (timeline)
  3. Sprint Board config: group_by=Status, card_fields=[Title, Priority, Assignee]
  4. Roadmap config: start_col=Start Date, end_col=Due Date, color_by=Status, group_by=Type
  5. UI: Schema tab renders all 12 column names in <thead>
  6. UI: Sprint Board + Roadmap view tabs visible

Usage:
    docker compose exec -T e2e pytest template/test_pm.py -v [--snapshot]
"""

import re
import time

import pytest

from e2e_base import BASE, api

PM_COLUMNS = [
    ("Title", "text"),
    ("Doc", "doc"),
    ("Type", "select"),
    ("Status", "select"),
    ("Priority", "select"),
    ("Assignee", "text"),
    ("Start Date", "date"),
    ("Due Date", "date"),
    ("Estimate", "number"),
    ("Tags", "tags"),
    ("Description", "text"),
    ("Parent", "text"),
]

TYPE_CHOICES = ["epic", "story", "task", "bug"]
STATUS_CHOICES = ["todo", "in_progress", "testing", "debugging", "review", "done", "merged"]
PRIORITY_CHOICES = ["critical", "high", "medium", "low"]


def test_pm_template_structure(authed_page, workspace, admin_token, snapshot):
    ws_id, ws_name = workspace
    suffix = int(time.time()) % 100000
    table_name = f"pm-tpl-{suffix}"

    # ── Step 1: Create PM template via API ───────────────────────────────────
    print("[1] POST /api/v1/tables/template/pm")
    r = api(
        "POST",
        "/api/v1/tables/template/pm",
        admin_token,
        json={"table_id": table_name, "workspace_id": ws_id},
    )
    assert r.status_code in (200, 201), (
        f"create PM template: {r.status_code} {r.text[:300]}"
    )

    data = r.json()
    columns = data.get("columns", [])
    views = data.get("views", [])

    # ── Step 2: Verify columns (API pillar) ──────────────────────────────────
    print(f"[2] Verify columns: got {len(columns)}")

    col_map = {c["name"]: c for c in columns}

    expected_names = [name for name, _ in PM_COLUMNS]
    missing = [n for n in expected_names if n not in col_map]
    assert not missing, f"missing columns: {missing}; got {list(col_map.keys())}"

    assert len(columns) == len(PM_COLUMNS), (
        f"expected {len(PM_COLUMNS)} columns, got {len(columns)}: "
        f"{[c['name'] for c in columns]}"
    )

    for name, expected_type in PM_COLUMNS:
        actual_type = col_map[name]["type"]
        assert actual_type == expected_type, (
            f"column '{name}': expected type '{expected_type}', got '{actual_type}'"
        )

    # Verify select column choices
    type_opts = col_map["Type"].get("options", {})
    type_values = [ch["value"] for ch in type_opts.get("choices", [])]
    assert type_values == TYPE_CHOICES, f"Type choices: expected {TYPE_CHOICES}, got {type_values}"

    status_opts = col_map["Status"].get("options", {})
    status_values = [ch["value"] for ch in status_opts.get("choices", [])]
    assert status_values == STATUS_CHOICES, f"Status choices: expected {STATUS_CHOICES}, got {status_values}"

    priority_opts = col_map["Priority"].get("options", {})
    priority_values = [ch["value"] for ch in priority_opts.get("choices", [])]
    assert priority_values == PRIORITY_CHOICES, f"Priority choices: expected {PRIORITY_CHOICES}, got {priority_values}"

    print("    columns OK")

    # ── Step 3: Verify views (API pillar) ─────────────────────────────────────
    print(f"[3] Verify views: got {len(views)}")
    assert len(views) == 2, f"expected 2 views, got {len(views)}: {views}"

    view_by_name = {v["name"]: v for v in views}
    assert "Sprint Board" in view_by_name, f"missing 'Sprint Board'; got {list(view_by_name.keys())}"
    assert "Roadmap" in view_by_name, f"missing 'Roadmap'; got {list(view_by_name.keys())}"

    sprint = view_by_name["Sprint Board"]
    assert sprint["type"] == "kanban", f"Sprint Board type: expected 'kanban', got '{sprint['type']}'"

    sprint_cfg = sprint.get("config", {})
    status_col_id = col_map["Status"]["column_id"]
    assert sprint_cfg.get("group_by") == status_col_id, (
        f"Sprint Board group_by: expected Status col_id '{status_col_id}', "
        f"got '{sprint_cfg.get('group_by')}'"
    )

    expected_card_fields = [
        col_map["Title"]["column_id"],
        col_map["Priority"]["column_id"],
        col_map["Assignee"]["column_id"],
    ]
    assert sprint_cfg.get("card_fields") == expected_card_fields, (
        f"Sprint Board card_fields mismatch: {sprint_cfg.get('card_fields')}"
    )

    roadmap = view_by_name["Roadmap"]
    assert roadmap["type"] == "timeline", f"Roadmap type: expected 'timeline', got '{roadmap['type']}'"

    roadmap_cfg = roadmap.get("config", {})
    assert roadmap_cfg.get("start_col") == col_map["Start Date"]["column_id"]
    assert roadmap_cfg.get("end_col") == col_map["Due Date"]["column_id"]
    assert roadmap_cfg.get("color_by") == col_map["Status"]["column_id"]
    assert roadmap_cfg.get("group_by") == col_map["Type"]["column_id"]

    # Verify default_view is Sprint Board
    default_view = data.get("default_view")
    assert default_view == sprint["view_id"], (
        f"default_view: expected {sprint['view_id']}, got {default_view}"
    )

    print("    views OK")

    # ── Step 4: UI verification ──────────────────────────────────────────────
    print("[4] UI: navigate to PM table")
    page = authed_page

    page.goto(f"{BASE}/{ws_name}/{table_name}", wait_until="networkidle")

    # Wait for views to load (Schema tab is auto-prepended)
    page.wait_for_selector("[data-testid='view-tab-Schema']", state="visible", timeout=10000)

    if snapshot:
        page.screenshot(path="/output/t55_01_pm_table_landing.png", full_page=True)

    # ── Step 5: verify view tabs exist ───────────────────────────────────
    print("[5] UI: verify view tabs")
    page.wait_for_selector(
        "[data-testid='view-tab-Sprint Board']", state="visible", timeout=5000
    )
    page.wait_for_selector(
        "[data-testid='view-tab-Roadmap']", state="visible", timeout=5000
    )
    print("    Sprint Board + Roadmap tabs visible")

    # ── Step 6: click Schema tab and verify column headers ───────────────
    print("[6] UI: click Schema tab, verify column headers")
    page.get_by_test_id("view-tab-Schema").click()
    page.wait_for_selector("table thead", state="visible", timeout=8000)

    if snapshot:
        page.screenshot(path="/output/t55_02_schema_view.png", full_page=True)

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
    assert not missing_in_ui, (
        f"columns missing from UI thead: {missing_in_ui}; rendered: {rendered_names}"
    )

    print(f"    all {len(expected_names)} columns rendered in thead")

    if snapshot:
        page.screenshot(path="/output/t55_03_columns_verified.png", full_page=True)

    print("PASS: e2e_test_template_pm")
