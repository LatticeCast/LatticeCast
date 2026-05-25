"""E2E test: workflow view — nodes render from rows, graph selector filters.

Topic: Workflow view renders table rows as SvelteFlow nodes. Graph
selector dropdown filters rows by graph_name column value.

Three pillars (developing-e2e):
  - Playwright UI    — workflow-view container visible, nodes rendered,
                       graph selector filters correctly
  - BE API verify    — rows exist in DB with correct row_data
  - Navigation check — workflow view persists after navigate away + back

Flow:
  setup:  login → create workspace → create blank table → add workflow
          columns (name, type, graph_name, nexts, pos_x, pos_y) →
          seed rows (3 nodes in "root", 2 in "sub") → create workflow view
  step 1: navigate to table → click Workflow tab → assert workflow-view
          container visible → assert 3 nodes visible (root graph default)
  step 2: select "sub" in graph selector → assert 2 nodes visible
  step 3: navigate away + back → assert workflow view still renders
  teardown: DELETE workspace (cascades)

Usage:
    docker compose exec -T e2e pytest table_views/test_workflow_nodes.py -v
    docker compose exec -T e2e pytest table_views/test_workflow_nodes.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


_TS = int(time.time())
TABLE_ID = f"wf-{_TS}"


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(
        f"{BASE}/{ws_id}/{table_id}",
        wait_until="domcontentloaded",
        timeout=20000,
    )
    try:
        page.wait_for_selector(
            '[data-table-loaded="true"]', timeout=15000
        )
    except PlaywrightTimeout:
        pytest.fail(f"Table page did not load for {table_id!r}")


def add_column(token: str, table_id: str, name: str, col_type: str,
               options: dict | None = None) -> str:
    body: dict = {"name": name, "type": col_type}
    if options:
        body["options"] = options
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json=body)
    assert r.status_code in (200, 201), (
        f"add column {name!r}: {r.status_code} {r.text[:200]}"
    )
    cols = r.json().get("columns", [])
    col = next((c for c in cols if c["name"] == name), None)
    assert col, f"column {name!r} not in response: {[c['name'] for c in cols]}"
    return col["column_id"]


def add_row(token: str, table_id: str, row_data: dict) -> int:
    r = api(
        "POST", f"/api/v1/tables/{table_id}/rows", token,
        json={"row_data": row_data},
    )
    assert r.status_code in (200, 201), (
        f"add row: {r.status_code} {r.text[:200]}"
    )
    return r.json()["row_id"]


def test_workflow_nodes(authed_page, admin_token, snapshot) -> None:
    token = admin_token
    page = authed_page

    # ── Setup: workspace ─────────────────────────────────────────────────
    ws_name = f"wf-test-{_TS}"
    r = api("POST", "/api/v1/workspaces", token,
            json={"workspace_name": ws_name})
    assert r.status_code == 201
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_id = ws_data["workspace_id"]
    print(f"[setup] workspace {ws_name!r} id={ws_uuid}")

    # ── Setup: blank table ───────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": ws_name})
    assert r.status_code == 201
    print(f"[setup] table {TABLE_ID!r}")

    try:
        # ── Setup: columns for workflow ──────────────────────────────────
        name_col = add_column(token, TABLE_ID, "name", "text")
        type_col = add_column(token, TABLE_ID, "type", "select", {
            "choices": [
                {"value": "START", "color": "green"},
                {"value": "STEP", "color": "blue"},
                {"value": "CONDITION", "color": "purple"},
            ]
        })
        graph_col = add_column(token, TABLE_ID, "graph_name", "select", {
            "choices": [
                {"value": "root", "color": "gray"},
                {"value": "sub", "color": "orange"},
            ]
        })
        nexts_col = add_column(token, TABLE_ID, "nexts", "text")
        pos_x_col = add_column(token, TABLE_ID, "pos_x", "number")
        pos_y_col = add_column(token, TABLE_ID, "pos_y", "number")
        print("[setup] columns created")

        # ── Setup: seed rows — 3 in "root", 2 in "sub" ──────────────────
        r1 = add_row(token, TABLE_ID, {
            name_col: "Start", type_col: "START",
            graph_col: "root", pos_x_col: 0, pos_y_col: 0,
            nexts_col: "[]",
        })
        r2 = add_row(token, TABLE_ID, {
            name_col: "Process", type_col: "STEP",
            graph_col: "root", pos_x_col: 250, pos_y_col: 0,
            nexts_col: "[]",
        })
        # Link Start → Process
        api("PUT", f"/api/v1/tables/{TABLE_ID}/rows/{r1}", token,
            json={"row_data": {
                name_col: "Start", type_col: "START",
                graph_col: "root", pos_x_col: 0, pos_y_col: 0,
                nexts_col: f'["{r2}"]',
            }})
        r3 = add_row(token, TABLE_ID, {
            name_col: "Check", type_col: "CONDITION",
            graph_col: "root", pos_x_col: 500, pos_y_col: 0,
            nexts_col: "[]",
        })
        # sub-graph nodes
        add_row(token, TABLE_ID, {
            name_col: "Sub Start", type_col: "START",
            graph_col: "sub", pos_x_col: 0, pos_y_col: 0,
            nexts_col: "[]",
        })
        add_row(token, TABLE_ID, {
            name_col: "Sub Step", type_col: "STEP",
            graph_col: "sub", pos_x_col: 250, pos_y_col: 0,
            nexts_col: "[]",
        })
        print(f"[setup] 5 rows seeded (3 root, 2 sub)")

        # ── Setup: create workflow view ──────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Workflow", "type": "workflow"})
        assert r.status_code in (200, 201), (
            f"create workflow view: {r.status_code} {r.text[:200]}"
        )
        print("[setup] workflow view created")

        # API pillar: verify rows exist
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows", token)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 5, f"expected 5 rows, got {len(rows)}"
        print(f"[ok] API: {len(rows)} rows in DB")

        # ── Step 1: navigate → click Workflow tab → nodes visible ────────
        goto_table(page, ws_id, TABLE_ID)
        print("[ok] navigated to table page")

        wf_tab = page.locator('[data-testid="view-tab-Workflow"]')
        try:
            wf_tab.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_tab", snapshot)
            pytest.fail("Workflow tab not visible")
        wf_tab.click()
        print("[ok] clicked Workflow tab")

        # Wait for workflow view container
        try:
            page.wait_for_selector(
                '[data-testid="workflow-view"]',
                state="visible", timeout=15000,
            )
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_view", snapshot)
            pytest.fail("workflow-view container not visible")
        print("[ok] workflow-view container visible")

        # Wait for SvelteFlow to render nodes
        try:
            page.wait_for_selector(
                '.svelte-flow__node', state="visible", timeout=10000,
            )
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_nodes", snapshot)
            pytest.fail("No SvelteFlow nodes rendered")

        # Default graph is "root" → 3 nodes
        nodes = page.locator('.svelte-flow__node')
        node_count = nodes.count()
        assert node_count == 3, (
            f"step 1: expected 3 root nodes, got {node_count}"
        )
        print(f"[ok] step 1 — UI: {node_count} nodes in root graph")
        snap(page, "wf_01_root_graph", snapshot)

        # Verify node labels exist
        for name in ["Start", "Process", "Check"]:
            loc = page.locator(
                f'[data-testid="workflow-node-{name}"]'
            )
            assert loc.count() >= 1, (
                f"step 1: node {name!r} not found"
            )
        print("[ok] step 1 — UI: all root node labels present")

        # ── Step 2: switch graph selector to "sub" ───────────────────────
        selector = page.locator(
            '[data-testid="workflow-graph-selector"]'
        )
        try:
            selector.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_selector", snapshot)
            pytest.fail("graph selector not visible")

        selector.select_option("sub")
        # Wait for nodes to update — sub graph has 2 nodes
        page.wait_for_timeout(1000)
        sub_nodes = page.locator('.svelte-flow__node')
        sub_count = sub_nodes.count()
        assert sub_count == 2, (
            f"step 2: expected 2 sub nodes, got {sub_count}"
        )
        print(f"[ok] step 2 — UI: {sub_count} nodes in sub graph")
        snap(page, "wf_02_sub_graph", snapshot)

        # ── Step 3: navigate away + back → workflow view persists ────────
        page.goto(
            f"{BASE}/{ws_id}/",
            wait_until="domcontentloaded", timeout=15000,
        )
        goto_table(page, ws_id, TABLE_ID)

        wf_tab2 = page.locator('[data-testid="view-tab-Workflow"]')
        try:
            wf_tab2.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_tab_after_nav", snapshot)
            pytest.fail("Workflow tab not visible after navigation")
        wf_tab2.click()

        try:
            page.wait_for_selector(
                '[data-testid="workflow-view"]',
                state="visible", timeout=15000,
            )
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_view_after_nav", snapshot)
            pytest.fail("workflow-view not visible after navigation")

        try:
            page.wait_for_selector(
                '.svelte-flow__node', state="visible", timeout=10000,
            )
        except PlaywrightTimeout:
            snap(page, "wf_FAIL_no_nodes_after_nav", snapshot)
            pytest.fail("No nodes rendered after navigation")

        nav_count = page.locator('.svelte-flow__node').count()
        assert nav_count > 0, "step 3: no nodes after navigation"
        print(f"[ok] step 3 — UI: {nav_count} nodes after navigation")
        snap(page, "wf_03_after_nav", snapshot)

    finally:
        r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
        if r.status_code not in (200, 204):
            print(f"warn: delete workspace returned {r.status_code}")
        else:
            print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — test_workflow_nodes ===")
