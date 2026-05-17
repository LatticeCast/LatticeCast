#!/usr/bin/env python3
"""E2E test: + Add row appears in all views.

Scenario:
  1. Create workspace + PM table (auto-creates Table, Sprint Board, Roadmap views).
  2. Navigate to Table view, click '+ Add row'.
  3. API verify: new row exists in backend.
  4. Update row with title, status, dates (needed for kanban lane + timeline bar).
  5. Reload page — verify row in Table view.
  6. Switch to Kanban (Sprint Board) — verify card.
  7. Switch to Timeline (Roadmap) — verify bar.
  8. Navigate away and back — verify persistence in all three views.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_row_create.py [--snapshot]
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
WORKSPACE_NAME = f"row-create-{_TS}"
TABLE_ID = f"row-create-{_TS}"

SNAPSHOT = "--snapshot" in sys.argv

ROW_TITLE = f"test-row-{_TS}"
ROW_STATUS = "todo"
ROW_START_DATE = "2026-06-01"
ROW_END_DATE = "2026-06-15"


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
            '[data-table-loaded="true"]', state="attached", timeout=15000
        )
    except PlaywrightTimeout:
        fatal(f"Table page did not load for {table_id}")


def switch_to_table_view(page) -> None:
    """Click the Schema (table) tab and wait for the grid to render."""
    page.locator('[data-testid="view-tab-Schema"]').click()
    page.locator('[data-testid="grid-add-row-btn"]').wait_for(
        state="visible", timeout=10000
    )


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
        # ── Setup: PM table ───────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        columns = schema.get("columns", [])
        views = schema.get("views", [])
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(columns)}, views={len(views)})")

        # Identify key columns
        title_col = next(
            (c for c in columns if c.get("name") == "Title" and c["type"] in ("text", "string")),
            next((c for c in columns if c["type"] in ("text", "string")), None),
        )
        status_col = next(
            (c for c in columns if c.get("name") == "Status" and c["type"] == "select"), None
        )
        if not title_col:
            fatal(f"No text column found: {[c['name'] for c in columns]}")
        if not status_col:
            fatal(f"No Status column found: {[c['name'] for c in columns]}")

        # Get view configs
        timeline_views = [v for v in views if v.get("type") == "timeline"]
        kanban_views = [v for v in views if v.get("type") == "kanban"]
        if not timeline_views:
            fatal(f"No timeline view; types={[v.get('type') for v in views]}")
        if not kanban_views:
            fatal(f"No kanban view; types={[v.get('type') for v in views]}")

        timeline_view = timeline_views[0]
        kanban_view = kanban_views[0]
        start_col_id = timeline_view.get("config", {}).get("start_col")
        end_col_id = timeline_view.get("config", {}).get("end_col")
        kanban_tab_name = kanban_view.get("name", "Sprint Board")
        timeline_tab_name = timeline_view.get("name", "Roadmap")

        if not start_col_id:
            fatal("Timeline view has no start_col configured")
        print(f"[ok] timeline: start_col={start_col_id!r}, end_col={end_col_id!r}")

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

            # ── Step 1: Click '+ Add row' in Table view ──────────────────────
            goto_table(page, ws_id, TABLE_ID)
            try:
                page.locator('[data-testid="view-tab-Schema"]').wait_for(
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                fatal("View tabs did not load")

            switch_to_table_view(page)
            snap(page, "row_create_01_table_view")

            new_row_id = None
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/rows" in resp.url
                    and resp.request.method == "POST"
                ),
                timeout=15000,
            ) as resp_info:
                page.locator('[data-testid="grid-add-row-btn"]').click()

            post_resp = resp_info.value
            if post_resp.status != 201:
                fatal(f"POST /rows returned {post_resp.status}")
            new_row_id = post_resp.json().get("row_id")
            if not new_row_id:
                fatal(f"POST /rows response missing row_id: {post_resp.json()}")
            print(f"[ok] POST /rows → row_id={new_row_id}")

            # ── Step 2: API verify — row exists ──────────────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{new_row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row {new_row_id}: {r.status_code} {r.text[:200]}")
            print(f"[ok] API: row {new_row_id} exists")

            # ── Step 3: Update row with title, status, dates ─────────────────
            row_data = {
                title_col["column_id"]: ROW_TITLE,
                status_col["column_id"]: ROW_STATUS,
                start_col_id: ROW_START_DATE,
            }
            if end_col_id:
                row_data[end_col_id] = ROW_END_DATE
            r = api(
                "PUT", f"/api/v1/tables/{TABLE_ID}/rows/{new_row_id}", token,
                json={"row_data": row_data},
            )
            if r.status_code != 200:
                fatal(f"PUT row {new_row_id}: {r.status_code} {r.text[:200]}")
            print(f"[ok] API: updated row with title/status/dates")

            # ── Step 4: Reload and verify in Table view ──────────────────────
            goto_table(page, ws_id, TABLE_ID)
            switch_to_table_view(page)

            row_sel = f'[data-testid="grid-row-{new_row_id}"]'
            try:
                page.locator(row_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_no_row_in_grid")
                fatal(f"Row {new_row_id} not visible in table grid")

            snap(page, "row_create_02_row_in_table")
            print(f"[ok] UI: row {new_row_id} visible in table grid")

            # ── Step 5: Switch to Kanban — verify card ───────────────────────
            kanban_tab = page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]')
            try:
                kanban_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                fatal(f"Kanban tab '{kanban_tab_name}' not visible")
            kanban_tab.click()

            try:
                page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_kanban_not_loaded")
                fatal("Kanban board did not load")

            card_sel = f'[data-testid="kanban-card-{new_row_id}-btn"]'
            try:
                page.locator(card_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_card_not_in_kanban")
                fatal(f"Card {new_row_id} not visible in kanban view")

            snap(page, "row_create_03_card_in_kanban")
            print(f"[ok] UI: card {new_row_id} visible in kanban ({kanban_tab_name})")

            # ── Step 6: Switch to Timeline — verify bar ──────────────────────
            timeline_tab = page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]')
            try:
                timeline_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                fatal(f"Timeline tab '{timeline_tab_name}' not visible")
            timeline_tab.click()

            bar_sel = f'[data-testid="timeline-row-bar-{new_row_id}"]'
            try:
                page.locator(bar_sel).wait_for(state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_bar_not_in_timeline")
                fatal(f"Bar {new_row_id} not visible in timeline view")

            snap(page, "row_create_04_bar_in_timeline")
            print(f"[ok] UI: bar {new_row_id} visible in timeline ({timeline_tab_name})")

            # ── Step 7: Navigate away and back — verify persistence ──────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            # API verify persistence
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{new_row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after nav: {r.status_code} {r.text[:200]}")
            persisted = r.json().get("row_data", {})
            if persisted.get(title_col["column_id"]) != ROW_TITLE:
                fatal(f"Title not persisted: {persisted.get(title_col['column_id'])!r}")
            if persisted.get(status_col["column_id"]) != ROW_STATUS:
                fatal(f"Status not persisted: {persisted.get(status_col['column_id'])!r}")
            print(f"[ok] API: row {new_row_id} data persists after navigation")

            # Table view persistence
            switch_to_table_view(page)
            try:
                page.locator(row_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_row_gone_table")
                fatal(f"Row {new_row_id} not in table after navigation")
            print(f"[ok] UI: row {new_row_id} persists in table after navigation")

            # Kanban persistence
            page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]').click()
            try:
                page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                fatal("Kanban board did not load after navigation")
            try:
                page.locator(card_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_card_gone_kanban")
                fatal(f"Card {new_row_id} not in kanban after navigation")
            print(f"[ok] UI: card {new_row_id} persists in kanban after navigation")

            # Timeline persistence
            page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]').click()
            try:
                page.locator(bar_sel).wait_for(state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "row_create_FAIL_bar_gone_timeline")
                fatal(f"Bar {new_row_id} not in timeline after navigation")
            print(f"[ok] UI: bar {new_row_id} persists in timeline after navigation")

            snap(page, "row_create_05_all_persisted")
            browser.close()

    finally:
        # ── Teardown: delete workspace ────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_row_create ===")


if __name__ == "__main__":
    main()
