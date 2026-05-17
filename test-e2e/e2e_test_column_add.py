#!/usr/bin/env python3
"""E2E test: e2e_test_column_add — new column shows everywhere.

Scenario:
  1. Create workspace + blank table with Status (select), Start/End (date)
     columns already in place, plus a Kanban ("Board") and a Timeline ("Gantt")
     view created via API.
  2. Navigate to the table — Schema view is the default for a blank table.
  3. Click '+ Add column', fill in a name (text type), submit.
  4. BE verify: column is present in the POST /columns response schema.
  5. UI verify (Table view): column header appears.
  6. Navigate to Board (Kanban view).
  7. UI verify (Kanban): column appears in the card-fields panel.
  8. Navigate to Gantt (Timeline view).
  9. UI verify (Timeline): column appears in the group_by select options
     (group_by accepts all column types — no type filter).
  10. Navigate away and back to the table.
  11. UI verify (Persistence): column header still visible in Table view.

Three pillars (developing-e2e-test v0.10.0):
  - Playwright UI    — header, kanban card-field checkbox, timeline group_by option
  - BE API verify    — POST /columns response carries the new column
  - Navigation check — navigate away + back; header persists

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_column_add.py [--snapshot]
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
_TS = int(time.time()) % 100000
WORKSPACE_NAME = f"col-add-{_TS}"
TABLE_ID = f"coladd-{_TS}"
NEW_COL_NAME = f"E2E Extra Field {_TS}"

SNAPSHOT = "--snapshot" in sys.argv


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


def _col_id(schema: dict, name: str) -> str:
    col = next((c for c in schema["columns"] if c["name"] == name), None)
    if col is None:
        fatal(f"column {name!r} not found in schema; have: {[c['name'] for c in schema['columns']]}")
    return col["column_id"]


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        fatal(f"View tabs did not load for table {table_id}")


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: workspace ──────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── Setup: blank table ────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_id})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        print(f"[ok] table {TABLE_ID!r}")

        # ── Setup: Status select column (for kanban group_by) ─────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Status", "type": "select",
                      "options": {"choices": [
                          {"value": "todo", "color": ""},
                          {"value": "done", "color": ""},
                      ]}})
        if r.status_code != 201:
            fatal(f"add Status col: {r.status_code} {r.text[:200]}")
        schema = r.json()
        status_col_id = _col_id(schema, "Status")
        print(f"[ok] Status col → {status_col_id}")

        # ── Setup: date columns (for timeline start/end) ───────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Start", "type": "date"})
        if r.status_code != 201:
            fatal(f"add Start col: {r.status_code} {r.text[:200]}")
        schema = r.json()
        start_col_id = _col_id(schema, "Start")
        print(f"[ok] Start col → {start_col_id}")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "End", "type": "date"})
        if r.status_code != 201:
            fatal(f"add End col: {r.status_code} {r.text[:200]}")
        schema = r.json()
        end_col_id = _col_id(schema, "End")
        print(f"[ok] End col → {end_col_id}")

        # ── Setup: Kanban view ────────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Board", "type": "kanban",
                      "config": {"group_by": status_col_id}})
        if r.status_code != 201:
            fatal(f"create Kanban view: {r.status_code} {r.text[:200]}")
        print("[ok] Kanban view 'Board'")

        # ── Setup: Timeline view ──────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Gantt", "type": "timeline",
                      "config": {"start_col": start_col_id, "end_col": end_col_id}})
        if r.status_code != 201:
            fatal(f"create Timeline view: {r.status_code} {r.text[:200]}")
        print("[ok] Timeline view 'Gantt'")

        # ── Playwright session ────────────────────────────────────────────────
        login_info = (
            '{"provider":"none",'
            f'"accessToken":"{token}",'
            f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
            '"role":"admin"}'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.connect(WS_URL)
            ctx = browser.new_context(viewport={"width": 1400, "height": 900})
            ctx.add_init_script(f"localStorage.setItem('loginInfo', {repr(login_info)});")
            page = ctx.new_page()

            # Schema view is the default for a blank table (no default_view set).
            goto_table(page, ws_id, TABLE_ID)
            snap(page, "col_add_01_table_loaded")
            print("[ok] table loaded (Schema view)")

            # ── Step 1: Open add-column modal ─────────────────────────────────
            # grid-add-column-btn appears in both TableHeader and TableGrid;
            # .first picks the first in DOM order.
            try:
                page.locator('[data-testid="grid-add-column-btn"]').first.wait_for(
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_no_add_btn")
                fatal("grid-add-column-btn not visible in Schema view")

            page.locator('[data-testid="grid-add-column-btn"]').first.click()

            try:
                page.wait_for_selector(
                    '[data-testid="add-column-name-input"]', state="visible", timeout=5000
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_no_modal")
                fatal("AddColumnModal did not open after clicking grid-add-column-btn")

            # Default type is 'text' — no interaction with type selector needed.
            page.fill('[data-testid="add-column-name-input"]', NEW_COL_NAME)
            snap(page, "col_add_02_modal_filled")
            print(f"[ok] filled column name {NEW_COL_NAME!r} (type=text)")

            # ── Step 2: Submit — capture POST response for BE pillar ──────────
            with page.expect_response(
                lambda resp: f"/api/v1/tables/{TABLE_ID}/columns" in resp.url
                and resp.request.method == "POST"
                and resp.ok,
                timeout=10000,
            ) as resp_info:
                page.click('[data-testid="add-column-submit-btn"]')

            post_schema = resp_info.value.json()
            cols_after = post_schema.get("columns", [])
            new_col = next((c for c in cols_after if c.get("name") == NEW_COL_NAME), None)
            if new_col is None:
                fatal(
                    f"[BE] column {NEW_COL_NAME!r} not in POST /columns response; "
                    f"columns={[c['name'] for c in cols_after]}"
                )
            new_col_id = new_col["column_id"]
            print(f"[ok] [BE] column present in POST schema (id={new_col_id})")

            # ── Step 3: Table view — column header visible ────────────────────
            try:
                page.wait_for_selector(
                    f'[data-testid="col-header-{new_col_id}"]',
                    state="visible",
                    timeout=5000,
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_no_table_header")
                fatal(f"[Table] col-header-{new_col_id} not visible after column add")
            snap(page, "col_add_03_table_header")
            print(f"[ok] [Table] col-header-{new_col_id} visible")

            # ── Step 4: Kanban view — column in card-fields panel ─────────────
            try:
                board_tab = page.locator('[data-testid="view-tab-Board"]')
                board_tab.wait_for(state="visible", timeout=10000)
                board_tab.click()
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_no_kanban_tab")
                fatal("Kanban tab 'Board' not visible")

            try:
                page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_kanban_no_render")
                fatal("Kanban board did not render (kanban-card-fields-btn not visible)")

            page.click('[data-testid="kanban-card-fields-btn"]')
            try:
                page.wait_for_selector(
                    f'[data-testid="kanban-card-field-{new_col_id}-checkbox"]',
                    state="visible",
                    timeout=5000,
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_kanban_no_field")
                fatal(
                    f"[Kanban] kanban-card-field-{new_col_id}-checkbox not in card-fields panel"
                )
            snap(page, "col_add_04_kanban_field")
            print(f"[ok] [Kanban] card-field-{new_col_id} present in fields panel")

            # ── Step 5: Timeline view — column in group_by select ─────────────
            try:
                gantt_tab = page.locator('[data-testid="view-tab-Gantt"]')
                gantt_tab.wait_for(state="visible", timeout=10000)
                gantt_tab.click()
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_no_timeline_tab")
                fatal("Timeline tab 'Gantt' not visible")

            try:
                page.wait_for_selector(
                    '[data-testid="timeline-group-by-select"]',
                    state="visible",
                    timeout=10000,
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_timeline_no_render")
                fatal("Timeline view did not render timeline-group-by-select")

            # group_by iterates ALL columns with no type filter — text col must appear.
            option_values = page.locator(
                '[data-testid="timeline-group-by-select"] option'
            ).evaluate_all("opts => opts.map(o => o.value)")
            if new_col_id not in option_values:
                snap(page, "col_add_FAIL_timeline_no_col")
                fatal(
                    f"[Timeline] column {new_col_id} not in group_by options: {option_values}"
                )
            snap(page, "col_add_05_timeline_group_by")
            print(f"[ok] [Timeline] column {new_col_id} present in group_by select")

            # ── Step 6: Persistence — navigate away and back ──────────────────
            page.goto(f"{BASE}/{ws_id}", wait_until="domcontentloaded")
            # Navigate back; the last-visited view (Gantt) may be restored as
            # default, so explicitly activate Schema to verify the col header.
            goto_table(page, ws_id, TABLE_ID)
            try:
                schema_tab = page.locator('[data-testid="view-tab-Schema"]')
                schema_tab.wait_for(state="visible", timeout=10000)
                schema_tab.click()
                page.wait_for_selector(
                    f'[data-testid="col-header-{new_col_id}"]',
                    state="visible",
                    timeout=5000,
                )
            except PlaywrightTimeout:
                snap(page, "col_add_FAIL_persistence")
                fatal(
                    f"[Persistence] col-header-{new_col_id} gone after navigate-away + back"
                )
            snap(page, "col_add_06_persistence")
            print(f"[ok] [Persistence] col-header-{new_col_id} visible after re-navigation")

            ctx.close()

        print("PASS  e2e_test_column_add")

    finally:
        api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        print(f"[ok] cleanup workspace {ws_id}")


if __name__ == "__main__":
    main()
