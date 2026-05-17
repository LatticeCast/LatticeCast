"""E2E test: e2e_test_view_timeline_color_by — color_by column change persists.

Topic: selecting a color_by column in a Timeline view paints bars with
per-choice colors, persists the selection to the DB, and survives navigation
away + back.

Three pillars (developing-e2e-test v0.10.0):
  - Playwright UI    — change [data-testid="timeline-color-by-select"]
  - BE API verify    — GET /api/v1/tables/{tid}/views/{vid} confirms config.color_by
  - Navigation check — navigate away and back; assert select + bar color persist

Bar color logic (timeline.utils.ts::getBarColorClasses):
  no color_by            → BAR_COLORS[0] = "bg-blue-400 text-white"
  color_by set, val=idx1 → BAR_COLORS[1] = "bg-green-400 text-white"

Test uses Status column with choices ["todo" (idx 0), "done" (idx 1)].
Row is created with Status="done" so bar must flip blue→green when color_by
is enabled — an unambiguous, observable change.

Two-container architecture:
  - This script runs in `test-e2e` (uv image, no Chromium).
  - Connects to `browser` via BROWSER_WS for UI actions.
  - Hits the BE through nginx (BASE_URL) for setup + DB-content verification.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_timeline_color_by.py [--snapshot]
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
WORKSPACE_NAME = f"tl-clr-{_SUFFIX}"
TABLE_ID = f"tlc-{_SUFFIX}"


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
        fatal(f"column {name!r} not found; columns={[c['name'] for c in schema['columns']]}")
    return col["column_id"]


def goto_table(page, ws_id: str, table_id: str) -> None:
    """Navigate to a table and wait for view tabs to render."""
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        fatal(f"View tabs did not load for table {table_id}")


def bar_classes(page, row_id: int) -> str:
    """Return the class attribute of the timeline bar for the given row_id."""
    return page.locator(f'[data-testid="timeline-row-bar-{row_id}"]').get_attribute("class") or ""


def main() -> None:
    snapshot = "--snapshot" in sys.argv
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create workspace ──────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── 2. Create blank table ────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_id})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        print(f"[ok] table {TABLE_ID!r}")

        # ── 3. Add date columns ──────────────────────────────────────────────
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

        # ── 4. Add select column with two choices ────────────────────────────
        # choices[0]="todo" → BAR_COLORS[0]="bg-blue-400" (same as default, no color_by)
        # choices[1]="done" → BAR_COLORS[1]="bg-green-400" (observable difference)
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

        # ── 5. Add a row with dates and status="done" ────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {
                    start_col_id: "2026-05-01",
                    end_col_id: "2026-05-15",
                    status_col_id: "done",
                }})
        if r.status_code != 201:
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] row row_id={row_id} (Start=2026-05-01, End=2026-05-15, Status='done')")

        # ── 6. Create timeline view (no color_by initially) ──────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Roadmap", "type": "timeline",
                      "config": {
                          "start_col": start_col_id,
                          "end_col": end_col_id,
                      }})
        if r.status_code != 201:
            fatal(f"create timeline view: {r.status_code} {r.text[:200]}")
        views = r.json().get("views", [])
        tl_view = next((v for v in views if v["name"] == "Roadmap"), None)
        if tl_view is None:
            fatal(f"Roadmap view not in response; views={[v['name'] for v in views]}")
        tl_view_id = tl_view["view_id"]
        initial_color_by = tl_view.get("config", {}).get("color_by")
        if initial_color_by is not None:
            fatal(f"expected no initial color_by, got {initial_color_by!r}")
        print(f"[ok] timeline view 'Roadmap' → view_id={tl_view_id} (no color_by)")

        # ── 7–10. UI + API pillars ───────────────────────────────────────────
        login_info = (
            '{"provider":"none",'
            f'"accessToken":"{token}",'
            f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
            '"role":"admin"}'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.connect(WS_URL)
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            page.goto(BASE, wait_until="domcontentloaded")
            page.evaluate("(info) => localStorage.setItem('loginInfo', info)", login_info)

            goto_table(page, ws_id, TABLE_ID)

            # ── step 1: navigate to Roadmap tab ─────────────────────────────
            try:
                roadmap_tab = page.locator('[data-testid="view-tab-Roadmap"]')
                roadmap_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_tab.png")
                fatal("Roadmap tab not visible")
            roadmap_tab.click()

            try:
                page.wait_for_selector(
                    '[data-testid="timeline-color-by-select"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_select.png")
                fatal("Color-by select not visible after clicking Roadmap tab")

            # Wait for the bar to render (row has valid dates)
            try:
                page.wait_for_selector(
                    f'[data-testid="timeline-row-bar-{row_id}"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_bar.png")
                fatal(f"Timeline bar for row_id={row_id} not visible")

            # UI pillar: no color_by → bar uses default blue
            cls_before = bar_classes(page, row_id)
            if "bg-blue-400" not in cls_before:
                fatal(f"UI step 1: bar class before color_by={cls_before!r}, expected 'bg-blue-400'")
            print("[ok] step 1 — UI: bar default class has 'bg-blue-400' (no color_by)")

            # UI pillar: color_by select is empty (no column selected)
            cb_val_before = page.locator('[data-testid="timeline-color-by-select"]').input_value()
            if cb_val_before != "":
                fatal(f"UI step 1: color_by select value={cb_val_before!r}, expected ''")
            print("[ok] step 1 — UI: color_by select is empty")

            if snapshot:
                page.screenshot(path="/output/tl_clr_01_before.png", full_page=True)

            # ── step 2: select Status in color_by; wait for PUT ──────────────
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                page.locator('[data-testid="timeline-color-by-select"]').select_option(status_col_id)
            print("[ok] selected Status in color_by; PUT confirmed")

            # UI pillar: color_by select reflects the new column
            cb_val_after = page.locator('[data-testid="timeline-color-by-select"]').input_value()
            if cb_val_after != status_col_id:
                fatal(f"UI step 2: color_by value={cb_val_after!r}, expected {status_col_id!r}")
            print("[ok] step 2 — UI: color_by select shows Status column")

            # UI pillar: bar is now green (Status="done" is idx=1 → BAR_COLORS[1])
            cls_after = bar_classes(page, row_id)
            if "bg-green-400" not in cls_after:
                fatal(f"UI step 2: bar class after color_by={cls_after!r}, expected 'bg-green-400'")
            print("[ok] step 2 — UI: bar class has 'bg-green-400' (Status='done', idx=1)")

            if snapshot:
                page.screenshot(path="/output/tl_clr_02_color_by_set.png", full_page=True)

            # API pillar: config.color_by persisted in DB
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
            got_color_by = r.json().get("config", {}).get("color_by")
            if got_color_by != status_col_id:
                fatal(f"API step 2: config.color_by={got_color_by!r}, expected {status_col_id!r}")
            print(f"[ok] step 2 — API: config.color_by confirmed in DB")

            # ── step 3: navigate away and back; verify persistence ────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                roadmap_tab2 = page.locator('[data-testid="view-tab-Roadmap"]')
                roadmap_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_tab_after_nav.png")
                fatal("Roadmap tab not visible after navigation back")
            roadmap_tab2.click()

            try:
                page.wait_for_selector(
                    '[data-testid="timeline-color-by-select"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_select_after_nav.png")
                fatal("Color-by select not visible after navigation back")

            # UI pillar: color_by select persisted across navigation
            cb_val_nav = page.locator('[data-testid="timeline-color-by-select"]').input_value()
            if cb_val_nav != status_col_id:
                fatal(
                    f"UI step 3 (after nav): color_by={cb_val_nav!r}, "
                    f"expected {status_col_id!r}"
                )
            print("[ok] step 3 — UI: color_by select still shows Status column after navigation")

            # Wait for the bar to render again
            try:
                page.wait_for_selector(
                    f'[data-testid="timeline-row-bar-{row_id}"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_clr_FAIL_no_bar_after_nav.png")
                fatal(f"Timeline bar for row_id={row_id} not visible after navigation back")

            # UI pillar: bar color persisted
            cls_nav = bar_classes(page, row_id)
            if "bg-green-400" not in cls_nav:
                fatal(
                    f"UI step 3 (after nav): bar class={cls_nav!r}, expected 'bg-green-400'"
                )
            print("[ok] step 3 — UI: bar color 'bg-green-400' persists across navigation")

            if snapshot:
                page.screenshot(path="/output/tl_clr_03_after_nav.png", full_page=True)

            # API pillar: color_by still in DB after navigation round-trip
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view after nav: {r.status_code} {r.text[:200]}")
            got_color_by2 = r.json().get("config", {}).get("color_by")
            if got_color_by2 != status_col_id:
                fatal(
                    f"API step 3 (after nav): config.color_by={got_color_by2!r}, "
                    f"expected {status_col_id!r}"
                )
            print("[ok] step 3 — API: config.color_by persisted after navigation")

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

    print("\n=== PASSED — e2e_test_view_timeline_color_by ===")


if __name__ == "__main__":
    main()
