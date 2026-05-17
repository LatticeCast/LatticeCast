#!/usr/bin/env python3
"""E2E test: Kanban drag card — drag a card between columns updates the row.

Scenario:
  1. Create workspace + PM table (auto-creates Sprint Board kanban view).
  2. Create a row in the "todo" lane.
  3. Navigate to the Sprint Board kanban view.
  4. Verify the card appears in the "todo" lane.
  5. Drag the card to the "in_progress" lane.
  6. Wait for PUT /rows/{row_id} to fire and resolve.
  7. API verify: row's Status field = "in_progress".
  8. UI verify: card appears in "in_progress" lane; absent from "todo" lane.
  9. Navigate away and back.
  10. API verify: row still has Status = "in_progress" (persisted in DB).
  11. UI verify: card is in "in_progress" lane after re-navigation.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_drag_card.py [--snapshot]
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
WORKSPACE_NAME = f"kb-drag-{_TS}"
TABLE_ID = f"kb-drag-{_TS}"

SNAPSHOT = "--snapshot" in sys.argv

SOURCE_LANE = "todo"
DEST_LANE = "in_progress"


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
        # ── Setup: PM table (auto-creates Sprint Board kanban view) ───────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        columns = schema.get("columns", [])
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(columns)})")

        # Find kanban view (Sprint Board)
        kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
        if not kanban_views:
            fatal(f"PM template has no kanban view; types={[v.get('type') for v in schema.get('views', [])]}")
        kanban_view = kanban_views[0]
        kanban_view_id = kanban_view["view_id"]
        group_by_col_id = kanban_view.get("config", {}).get("group_by")
        if not group_by_col_id:
            fatal("Kanban view has no group_by configured")
        print(f"[ok] kanban view_id={kanban_view_id}  group_by={group_by_col_id!r}")

        # Verify source and destination lane values exist as choices
        status_col = next((c for c in columns if c["column_id"] == group_by_col_id), None)
        if not status_col:
            fatal(f"Could not find group_by column {group_by_col_id!r} in schema")
        choices = [ch["value"] for ch in status_col.get("options", {}).get("choices", [])]
        if SOURCE_LANE not in choices or DEST_LANE not in choices:
            fatal(f"Expected choices {SOURCE_LANE!r},{DEST_LANE!r} in {choices}")
        print(f"[ok] status choices include {SOURCE_LANE!r} and {DEST_LANE!r}")

        # Create a row in the source lane
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {group_by_col_id: SOURCE_LANE}})
        if r.status_code != 201:
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] created row {row_id} in {SOURCE_LANE!r} lane")

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

            goto_table(page, ws_id, TABLE_ID)

            # ── Step 1: Navigate to Sprint Board tab ──────────────────────────
            try:
                sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_tab")
                fatal("Sprint Board tab not visible")
            sprint_tab.click()
            print("[ok] clicked Sprint Board tab")

            # Wait for kanban to render (card-fields button is the sentinel)
            try:
                cf_btn = page.locator('[data-testid="kanban-card-fields-btn"]')
                cf_btn.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_kanban")
                fatal("Kanban card-fields button not visible — board did not render")

            snap(page, "kb_drag_01_kanban_loaded")
            print("[ok] kanban view loaded")

            # ── Step 2: Verify card is in source lane ─────────────────────────
            source_lane = page.locator(f'[data-testid="kanban-lane-{SOURCE_LANE}"]')
            try:
                source_lane.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_source_lane")
                fatal(f"Source lane (data-testid=kanban-lane-{SOURCE_LANE}) not visible")

            card_sel = f'[data-testid="kanban-card-{row_id}-btn"]'
            card_in_source = source_lane.locator(card_sel)
            try:
                card_in_source.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_card_not_in_source")
                fatal(f"Card {row_id} not visible in {SOURCE_LANE!r} lane before drag")

            snap(page, "kb_drag_02_card_in_source")
            print(f"[ok] card {row_id} visible in {SOURCE_LANE!r} lane")

            # ── Step 3: Drag card to destination lane ─────────────────────────
            dest_lane = page.locator(f'[data-testid="kanban-lane-{DEST_LANE}"]')
            try:
                dest_lane.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_dest_lane")
                fatal(f"Destination lane (data-testid=kanban-lane-{DEST_LANE}) not visible")

            card_el = page.locator(card_sel)
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/rows/{row_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=15000,
            ):
                card_el.drag_to(dest_lane)

            print(f"[ok] dragged card {row_id} to {DEST_LANE!r} — PUT fired")

            # ── Step 4: API verify — row's status updated ─────────────────────
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row: {r.status_code} {r.text[:200]}")
            row_data = r.json().get("row_data", {})
            actual_val = row_data.get(group_by_col_id)
            if actual_val != DEST_LANE:
                fatal(
                    f"API: row {row_id} has {group_by_col_id!r}={actual_val!r}, "
                    f"expected {DEST_LANE!r}"
                )
            print(f"[ok] API: row {row_id} status={DEST_LANE!r}")

            # ── Step 5: UI verify — card in dest lane, absent from source ─────
            card_in_dest = dest_lane.locator(card_sel)
            try:
                card_in_dest.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_card_not_in_dest")
                fatal(f"Card {row_id} not visible in {DEST_LANE!r} lane after drag")

            card_in_source_after = source_lane.locator(card_sel)
            try:
                card_in_source_after.wait_for(state="hidden", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_card_still_in_source")
                fatal(f"Card {row_id} still visible in {SOURCE_LANE!r} lane after drag")

            snap(page, "kb_drag_03_card_in_dest")
            print(f"[ok] UI: card {row_id} in {DEST_LANE!r}, absent from {SOURCE_LANE!r}")

            # ── Step 6: Navigate away and back → verify persistence ───────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_tab_after_nav")
                fatal("Sprint Board tab not visible after navigation back")
            sprint_tab2.click()

            try:
                cf_btn2 = page.locator('[data-testid="kanban-card-fields-btn"]')
                cf_btn2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_kanban_after_nav")
                fatal("Kanban board not visible after navigation back")

            # API verify persistence
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}", token)
            if r.status_code != 200:
                fatal(f"GET row after nav: {r.status_code} {r.text[:200]}")
            row_data_after = r.json().get("row_data", {})
            actual_val_after = row_data_after.get(group_by_col_id)
            if actual_val_after != DEST_LANE:
                fatal(
                    f"Persistence: row {row_id} has {group_by_col_id!r}={actual_val_after!r}, "
                    f"expected {DEST_LANE!r}"
                )
            print(f"[ok] API: row {row_id} status persisted as {DEST_LANE!r} after navigation")

            # UI verify persistence
            dest_lane2 = page.locator(f'[data-testid="kanban-lane-{DEST_LANE}"]')
            try:
                dest_lane2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_no_dest_after_nav")
                fatal(f"Dest lane {DEST_LANE!r} not visible after navigation back")

            card_in_dest2 = dest_lane2.locator(card_sel)
            try:
                card_in_dest2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_drag_FAIL_card_not_persisted")
                fatal(
                    f"Card {row_id} not visible in {DEST_LANE!r} lane after navigation back"
                )

            snap(page, "kb_drag_04_persisted")
            print(f"[ok] UI: card {row_id} persists in {DEST_LANE!r} lane after navigation")

            browser.close()

    finally:
        # ── Teardown: delete workspace ────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_kanban_drag_card ===")


if __name__ == "__main__":
    main()
