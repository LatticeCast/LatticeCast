"""
E2E test: Workflow template structure (11 columns, 1 view).

Verifies:
  1. POST /api/v1/tables/template/workflow → 11 columns with correct
     names+types
  2. Response includes 1 view: Workflow (workflow)
  3. default_view points to the Workflow view
  4. type column has correct node-type choices
  5. graph_name column has "root" choice
  6. UI: Schema tab renders all 11 column names in <thead>
  7. UI: Workflow view tab visible

Usage:
    docker compose exec -T e2e pytest template/test_workflow.py -v [--snapshot]
"""

import re
import time

import pytest

from e2e_base import BASE, api

WF_COLUMNS = [
    ("Title",       "text"),
    ("name",        "text"),
    ("type",        "select"),
    ("description", "text"),
    ("graph_name",  "select"),
    ("nexts",       "text"),
    ("true_next",   "text"),
    ("false_next",  "text"),
    ("pos_x",       "number"),
    ("pos_y",       "number"),
]

TYPE_CHOICES = ["START", "STEP", "TOOL", "CONDITION", "INFO", "SUBGRAPH"]
GRAPH_NAME_CHOICES = ["root"]


def test_workflow_template_structure(authed_page, workspace, admin_token, snapshot):
    ws_id, ws_name = workspace
    suffix = int(time.time()) % 100000
    table_name = f"wf-tpl-{suffix}"

    # ── Step 1: Create workflow template via API ─────────────────────────
    print("[1] POST /api/v1/tables/template/workflow")
    r = api(
        "POST",
        "/api/v1/tables/template/workflow",
        admin_token,
        json={"table_id": table_name, "workspace_id": ws_id},
    )
    assert r.status_code in (200, 201), (
        f"create workflow template: {r.status_code} {r.text[:300]}"
    )

    data = r.json()
    columns = data.get("columns", [])
    views = data.get("views", [])

    # ── Step 2: Verify columns (API pillar) ──────────────────────────────
    print(f"[2] Verify columns: got {len(columns)}")

    col_map = {c["name"]: c for c in columns}

    expected_names = [name for name, _ in WF_COLUMNS]
    missing = [n for n in expected_names if n not in col_map]
    assert not missing, f"missing columns: {missing}; got {list(col_map.keys())}"

    for name, expected_type in WF_COLUMNS:
        actual_type = col_map[name]["type"]
        assert actual_type == expected_type, (
            f"column '{name}': expected type '{expected_type}', "
            f"got '{actual_type}'"
        )

    # Verify type column choices
    type_opts = col_map["type"].get("options", {})
    type_values = [ch["value"] for ch in type_opts.get("choices", [])]
    assert type_values == TYPE_CHOICES, (
        f"type choices: expected {TYPE_CHOICES}, got {type_values}"
    )

    # Verify graph_name column choices
    gn_opts = col_map["graph_name"].get("options", {})
    gn_values = [ch["value"] for ch in gn_opts.get("choices", [])]
    assert gn_values == GRAPH_NAME_CHOICES, (
        f"graph_name choices: expected {GRAPH_NAME_CHOICES}, "
        f"got {gn_values}"
    )

    print("    columns OK")

    # ── Step 3: Verify views (API pillar) ────────────────────────────────
    print(f"[3] Verify views: got {len(views)}")
    assert len(views) == 1, f"expected 1 view, got {len(views)}: {views}"

    wf_view = views[0]
    assert wf_view["name"] == "Workflow", (
        f"view name: expected 'Workflow', got '{wf_view['name']}'"
    )
    assert wf_view["type"] == "workflow", (
        f"view type: expected 'workflow', got '{wf_view['type']}'"
    )

    default_view = data.get("default_view")
    assert default_view == wf_view["view_id"], (
        f"default_view: expected {wf_view['view_id']}, got {default_view}"
    )

    print("    views OK")

    # ── Step 4: UI verification ──────────────────────────────────────────
    print("[4] UI: navigate to workflow table")
    page = authed_page

    page.goto(
        f"{BASE}/{ws_name}/{table_name}",
        wait_until="networkidle",
    )
    page.wait_for_selector(
        "[data-testid='view-tab-Schema']",
        state="visible", timeout=10000,
    )

    if snapshot:
        page.screenshot(
            path="/output/wf_tpl_01_landing.png", full_page=True,
        )

    # ── Step 5: verify Workflow view tab exists ──────────────────────────
    print("[5] UI: verify Workflow tab")
    page.wait_for_selector(
        "[data-testid='view-tab-Workflow']",
        state="visible", timeout=5000,
    )
    print("    Workflow tab visible")

    # ── Step 6: click Schema tab and verify column headers ───────────────
    print("[6] UI: click Schema tab, verify column headers")
    page.get_by_test_id("view-tab-Schema").click()
    page.wait_for_selector("table thead", state="visible", timeout=8000)

    if snapshot:
        page.screenshot(
            path="/output/wf_tpl_02_schema_view.png", full_page=True,
        )

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
        f"columns missing from UI thead: {missing_in_ui}; "
        f"rendered: {rendered_names}"
    )

    print(f"    all {len(expected_names)} columns rendered in thead")

    if snapshot:
        page.screenshot(
            path="/output/wf_tpl_03_columns_verified.png", full_page=True,
        )

    print("PASS: test_workflow_template_structure")
