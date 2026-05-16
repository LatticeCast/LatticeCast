#!/usr/bin/env python3
"""
E2E test: e2e_test_view_kanban_groupby — group_by change persists across navigation.

Topic: Kanban view group_by selector — UI change updates DB config; round-trip
navigation proves the setting is durable, not in-memory only.

Three pillars (developing-e2e-test v0.8.0):
  - Playwright UI    — select group_by via [data-testid="group-by-selector"]
  - BE API verify    — GET /api/v1/tables/{tid}/views/{vid} confirms config.group_by
  - Navigation check — navigate away to workspace root and back; assert selector
                       still shows the persisted column (state is not local-only)

Two-container architecture:
  - This script runs in `test-e2e` (uv image, no Chromium).
  - Connects to `browser` via BROWSER_WS for UI actions.
  - Hits the BE through nginx (BASE_URL) for setup + DB-content verification.

Flow:
  setup:  login as "lattice" → create workspace → create PM table (Sprint Board
          kanban view auto-created with group_by=Status)
  step 1: navigate to table → click Sprint Board tab → assert selector visible
          → UI confirm initial group_by
  step 2: select a different select column → wait for PUT → UI + API verify
  step 3: navigate away and back → click Sprint Board again → UI + API verify persists
  teardown: DELETE workspace (cascades tables + views)

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_groupby.py
    docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_groupby.py --snapshot
"""

from __future__ import annotations

import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WORKSPACE_NAME = f"kb-grp-{_SUFFIX}"
TABLE_ID = f"kb-{_SUFFIX}"

# Vite dev mode bakes in localhost as the backend URL.
# In the browser container, localhost != lattice-cast, so we rewrite.
_FRONTEND_BE = BASE.replace("lattice-cast", "localhost")


def fatal(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def login(user_name: str) -> str:
    r = requests.post(
        f"{BASE}/api/v1/login/password",
        json={"user_name": user_name, "password": ""},
        timeout=10,
    )
    if r.status_code != 200:
        fatal(f"login {user_name!r}: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def goto_table(page, ws_id: str, table_id: str) -> None:
    """Navigate to a table and wait for view tabs to render."""
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        fatal(f"View tabs did not load for table {table_id}")


def main() -> None:
    snapshot = "--snapshot" in sys.argv
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create fresh workspace ─────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── 2. Create PM table — auto-creates Sprint Board (kanban, group_by=Status)
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(schema['columns'])})")

        # API verify: Sprint Board kanban view exists with initial group_by
        kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
        if not kanban_views:
            fatal(
                f"PM template produced no kanban view; "
                f"types={[v.get('type') for v in schema.get('views', [])]}"
            )
        kanban_view = kanban_views[0]
        kanban_view_id = kanban_view["view_id"]
        initial_group_by = kanban_view.get("config", {}).get("group_by")
        if not initial_group_by:
            fatal(f"PM kanban view has no initial group_by: {kanban_view.get('config')}")
        print(f"[ok] kanban view_id={kanban_view_id}  initial group_by={initial_group_by!r}")

        # Pick a DIFFERENT select column to switch to (PM has Type, Status, Priority)
        select_cols = [
            c for c in schema.get("columns", [])
            if c.get("type") == "select" and c.get("column_id") != initial_group_by
        ]
        if not select_cols:
            fatal(
                f"Need ≥2 select columns to test switch; found: "
                f"{[(c.get('name'), c.get('type')) for c in schema.get('columns', [])]}"
            )
        new_col = select_cols[0]
        new_col_id: str = new_col["column_id"]
        print(f"[ok] will switch group_by → {new_col['name']!r} ({new_col_id})")

        # ── 3–7. UI + API pillars inside a Playwright session ─────────────────
        login_info = (
            '{"provider":"none",'
            f'"accessToken":"{token}",'
            f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
            '"role":"admin"}'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.connect(WS_URL)
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            # Rewrite localhost → lattice-cast for Vite dev API calls.
            if _FRONTEND_BE != BASE:
                def _reroute(route):
                    route.continue_(url=route.request.url.replace(_FRONTEND_BE, BASE))
                page.route(f"{_FRONTEND_BE}/**", _reroute)

            # Inject auth into localStorage before navigating to the table
            page.goto(BASE, wait_until="domcontentloaded")
            page.evaluate("(info) => localStorage.setItem('loginInfo', info)", login_info)

            goto_table(page, ws_id, TABLE_ID)

            # ── step 1: click Sprint Board tab → confirm group-by selector visible
            try:
                sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/kb_groupby_FAIL_no_tab.png")
                fatal("Sprint Board tab not visible — view tabs may not have loaded")
            sprint_tab.click()
            print("[ok] clicked Sprint Board tab")

            try:
                grp_select = page.locator('[data-testid="group-by-selector"]')
                grp_select.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/kb_groupby_FAIL_no_selector.png")
                fatal("group-by-selector not visible after clicking Sprint Board tab")

            # UI pillar: initial group_by matches the DB value from setup
            current_val = grp_select.input_value()
            if current_val != initial_group_by:
                fatal(
                    f"UI step 1: group-by shows {current_val!r}, "
                    f"expected initial {initial_group_by!r}"
                )
            print(f"[ok] step 1 — UI: initial group_by={current_val!r} matches DB")

            if snapshot:
                page.screenshot(path="/output/kb_groupby_01_initial.png", full_page=True)

            # ── step 2: change group_by; wait for PUT; verify UI + API ──────────
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                page.select_option('[data-testid="group-by-selector"]', new_col_id)
            print(f"[ok] selected {new_col['name']!r} ({new_col_id}) as group_by; PUT confirmed")

            # UI pillar
            ui_val = grp_select.input_value()
            if ui_val != new_col_id:
                fatal(f"UI step 2: group-by shows {ui_val!r}, expected {new_col_id!r}")
            print(f"[ok] step 2 — UI: group_by={ui_val!r}")

            if snapshot:
                page.screenshot(path="/output/kb_groupby_02_changed.png", full_page=True)

            # API pillar
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view {kanban_view_id}: {r.status_code} {r.text[:200]}")
            got_group_by = r.json().get("config", {}).get("group_by")
            if got_group_by != new_col_id:
                fatal(f"API step 2: config.group_by={got_group_by!r}, expected {new_col_id!r}")
            print(f"[ok] step 2 — API: config.group_by={got_group_by!r} confirmed in DB")

            # ── step 3: navigate away and back; verify persistence ────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            goto_table(page, ws_id, TABLE_ID)

            try:
                sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/kb_groupby_FAIL_no_tab_after_nav.png")
                fatal("Sprint Board tab not visible after navigation back")
            sprint_tab2.click()

            try:
                grp_select2 = page.locator('[data-testid="group-by-selector"]')
                grp_select2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/kb_groupby_FAIL_no_selector_after_nav.png")
                fatal("group-by-selector not visible after navigation back")

            selected_val = grp_select2.input_value()
            if selected_val != new_col_id:
                fatal(
                    f"UI step 3 (after nav): group_by shows {selected_val!r}, "
                    f"expected {new_col_id!r}"
                )
            print("[ok] step 3 — UI: group_by persists across navigation")

            if snapshot:
                page.screenshot(path="/output/kb_groupby_03_after_nav.png", full_page=True)

            # API pillar after round-trip navigation
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view after nav: {r.status_code} {r.text[:200]}")
            got_group_by2 = r.json().get("config", {}).get("group_by")
            if got_group_by2 != new_col_id:
                fatal(
                    f"API step 3 (after nav): config.group_by={got_group_by2!r}, "
                    f"expected {new_col_id!r}"
                )
            print(f"[ok] step 3 — API: config.group_by={got_group_by2!r} persisted after nav")

            browser.close()

    finally:
        # ── Teardown: delete workspace (cascades tables + views) ──────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            listed = {w["workspace_name"] for w in api("GET", "/api/v1/workspaces", token).json()}
            if WORKSPACE_NAME in listed:
                print(f"WARN: workspace {WORKSPACE_NAME!r} still listed after DELETE", file=sys.stderr)
            else:
                print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_kanban_groupby ===")


if __name__ == "__main__":
    main()
