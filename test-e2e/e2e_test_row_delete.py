#!/usr/bin/env python3
"""E2E test: delete row disappears everywhere.

Scenario:
  1. Create workspace + PM table (auto-creates Table, Sprint Board, Roadmap views).
  2. Create a row via API with title, status, dates (visible in all views).
  3. Navigate to Table view — verify row visible.
  4. Switch to Kanban — verify card visible.
  5. Switch to Timeline — verify bar visible.
  6. Switch back to Table view.
  7. Click delete button on the row.
  8. API verify: row returns 404.
  9. UI verify: row gone from Table view.
  10. Switch to Kanban — verify card gone.
  11. Switch to Timeline — verify bar gone.
  12. Navigate away and back — verify still gone everywhere.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_row_delete.py [--snapshot]
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
WORKSPACE_NAME = f"row-delete-{_TS}"
TABLE_ID = f"row-delete-{_TS}"

SNAPSHOT = "--snapshot" in sys.argv

ROW_TITLE = f"delete-me-{_TS}"
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

        # ── Setup: create row via API ─────────────────────────────────────────
        row_data = {
            title_col["column_id"]: ROW_TITLE,
            status_col["column_id"]: ROW_STATUS,
            start_col_id: ROW_START_DATE,
        }
        if end_col_id:
            row_data[end_col_id] = ROW_END_DATE

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": row_data})
        if r.status_code != 201:
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] created row {row_id} with title={ROW_TITLE!r}")

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

            # ── Step 1: Verify row in Table view ──────────────────────────────
            goto_table(page, ws_id, TABLE_ID)
            switch_to_table_view(page)

            row_sel = f'[data-testid="grid-row-{row_id}"]'
            try:
                page.locator(row_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_delete_FAIL_row_not_in_grid")
                fatal(f"Row {row_id} not visible in table grid (pre-delete)")
            snap(page, "row_delete_01_row_in_table")
            print(f"[ok] UI: row {row_id} visible in table grid")

            # ── Step 2: Verify card in Kanban ─────────────────────────────────
            kanban_tab = page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]')
            kanban_tab.wait_for(state="visible", timeout=10000)
            kanban_tab.click()

            page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                state="visible", timeout=10000
            )

            card_sel = f'[data-testid="kanban-card-{row_id}-btn"]'
            try:
                page.locator(card_sel).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_delete_FAIL_card_not_in_kanban")
                fatal(f"Card {row_id} not visible in kanban (pre-delete)")
            snap(page, "row_delete_02_card_in_kanban")
            print(f"[ok] UI: card {row_id} visible in kanban")

            # ── Step 3: Verify bar in Timeline ────────────────────────────────
            timeline_tab = page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]')
            timeline_tab.wait_for(state="visible", timeout=10000)
            timeline_tab.click()

            bar_sel = f'[data-testid="timeline-row-bar-{row_id}"]'
            try:
                page.locator(bar_sel).wait_for(state="visible", timeout=15000)
            except PlaywrightTimeout:
                snap(page, "row_delete_FAIL_bar_not_in_timeline")
                fatal(f"Bar {row_id} not visible in timeline (pre-delete)")
            snap(page, "row_delete_03_bar_in_timeline")
            print(f"[ok] UI: bar {row_id} visible in timeline")

            # ── Step 4: Switch to Table view, click delete ────────────────────
            switch_to_table_view(page)
            page.locator(row_sel).wait_for(state="visible", timeout=10000)

            delete_btn = page.locator(f'[data-testid="grid-delete-row-{row_id}-btn"]')
            delete_btn.wait_for(state="visible", timeout=10000)

            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/rows/{row_id}" in resp.url
                    and resp.request.method == "DELETE"
                ),
                timeout=15000,
            ) as resp_info:
                delete_btn.click()

            del_resp = resp_info.value
            if del_resp.status != 204:
                fatal(f"DELETE /rows/{row_id} returned {del_resp.status}")
            snap(page, "row_delete_04_after_click")
            print(f"[ok] DELETE /rows/{row_id} → 204")

            # ── Step 5: API verify — row gone ─────────────────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 404:
                fatal(f"GET row {row_id} after delete: expected 404, got {r.status_code}")
            print(f"[ok] API: row {row_id} returns 404")

            # ── Step 6: UI verify — row gone from Table view ──────────────────
            try:
                page.locator(row_sel).wait_for(state="detached", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "row_delete_FAIL_row_still_in_grid")
                fatal(f"Row {row_id} still visible in table grid after delete")
            snap(page, "row_delete_05_row_gone_table")
            print(f"[ok] UI: row {row_id} gone from table grid")

            # ── Step 7: Switch to Kanban — verify card gone ───────────────────
            page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]').click()
            page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                state="visible", timeout=10000
            )

            card_count = page.locator(card_sel).count()
            if card_count != 0:
                snap(page, "row_delete_FAIL_card_still_in_kanban")
                fatal(f"Card {row_id} still visible in kanban after delete")
            snap(page, "row_delete_06_card_gone_kanban")
            print(f"[ok] UI: card {row_id} gone from kanban")

            # ── Step 8: Switch to Timeline — verify bar gone ──────────────────
            page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]').click()
            page.locator('[data-testid="timeline-add-row-btn"]').wait_for(
                state="visible", timeout=10000
            )

            bar_count = page.locator(bar_sel).count()
            if bar_count != 0:
                snap(page, "row_delete_FAIL_bar_still_in_timeline")
                fatal(f"Bar {row_id} still visible in timeline after delete")
            snap(page, "row_delete_07_bar_gone_timeline")
            print(f"[ok] UI: bar {row_id} gone from timeline")

            # ── Step 9: Navigate away and back — verify still gone ────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            # API still 404
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 404:
                fatal(f"GET row after nav: expected 404, got {r.status_code}")
            print(f"[ok] API: row {row_id} still 404 after navigation")

            # Table view — row still gone
            switch_to_table_view(page)
            row_count = page.locator(row_sel).count()
            if row_count != 0:
                snap(page, "row_delete_FAIL_row_reappeared_table")
                fatal(f"Row {row_id} reappeared in table after navigation")
            print(f"[ok] UI: row {row_id} still gone from table after navigation")

            # Kanban — card still gone
            page.locator(f'[data-testid="view-tab-{kanban_tab_name}"]').click()
            page.locator('[data-testid="kanban-card-fields-btn"]').wait_for(
                state="visible", timeout=10000
            )
            card_count = page.locator(card_sel).count()
            if card_count != 0:
                snap(page, "row_delete_FAIL_card_reappeared_kanban")
                fatal(f"Card {row_id} reappeared in kanban after navigation")
            print(f"[ok] UI: card {row_id} still gone from kanban after navigation")

            # Timeline — bar still gone
            page.locator(f'[data-testid="view-tab-{timeline_tab_name}"]').click()
            page.locator('[data-testid="timeline-add-row-btn"]').wait_for(
                state="visible", timeout=10000
            )
            bar_count = page.locator(bar_sel).count()
            if bar_count != 0:
                snap(page, "row_delete_FAIL_bar_reappeared_timeline")
                fatal(f"Bar {row_id} reappeared in timeline after navigation")
            print(f"[ok] UI: bar {row_id} still gone from timeline after navigation")

            snap(page, "row_delete_08_all_gone_after_nav")
            browser.close()

    finally:
        # ── Teardown: delete workspace ────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_row_delete ===")


if __name__ == "__main__":
    main()
