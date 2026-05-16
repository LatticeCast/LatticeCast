"""E2E test: e2e_test_view_timeline_groupby — timeline group_by persists.

Topic: changing the group_by column in a Timeline view persists to the DB
and survives navigation away + back.

Three pillars (developing-e2e-test v0.8.0):
  - Playwright UI    — select group_by via [data-testid="timeline-group-by-select"]
  - BE API verify    — GET /api/v1/tables/{tid}/views/{vid} confirms config.group_by
  - Navigation check — navigate away to workspace page and back, assert select
                       still shows the persisted column (negative: state is not
                       local-only)

Two-container architecture:
  - This script runs in `test-e2e` (uv image, no Chromium).
  - Connects to `browser` via BROWSER_WS for UI actions.
  - Hits the BE through nginx (BASE_URL) for setup + DB-content verification.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_timeline_groupby.py [--snapshot]
"""

from __future__ import annotations

import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from e2e_base import install_be_reroute

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WORKSPACE_NAME = f"tl-grp-{_SUFFIX}"
TABLE_ID = f"tl-{_SUFFIX}"

# Vite dev mode bakes in localhost as the backend URL.
# In the browser container, localhost != lattice-cast, so we rewrite.


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

        # ── 3. Add date + select columns ─────────────────────────────────────
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

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Status", "type": "select",
                      "options": {"choices": [{"label": "Todo"}, {"label": "Done"}]}})
        if r.status_code != 201:
            fatal(f"add Status col: {r.status_code} {r.text[:200]}")
        schema = r.json()
        status_col_id = _col_id(schema, "Status")
        print(f"[ok] Status col → {status_col_id}")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Category", "type": "select",
                      "options": {"choices": [{"label": "A"}, {"label": "B"}]}})
        if r.status_code != 201:
            fatal(f"add Category col: {r.status_code} {r.text[:200]}")
        schema = r.json()
        category_col_id = _col_id(schema, "Category")
        print(f"[ok] Category col → {category_col_id}")

        # ── 4. Create timeline view with start/end + initial group_by=Status ────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
                json={"name": "Roadmap", "type": "timeline",
                      "config": {
                          "start_col": start_col_id,
                          "end_col": end_col_id,
                          "group_by": status_col_id,
                      }})
        if r.status_code != 201:
            fatal(f"create timeline view: {r.status_code} {r.text[:200]}")
        views = r.json().get("views", [])
        tl_view = next((v for v in views if v["name"] == "Roadmap"), None)
        if tl_view is None:
            fatal(f"Roadmap view not in response; views={[v['name'] for v in views]}")
        tl_view_id = tl_view["view_id"]
        initial_group_by = tl_view.get("config", {}).get("group_by")
        print(f"[ok] timeline view 'Roadmap' → view_id={tl_view_id}, group_by={initial_group_by!r}")

        # API verify: initial group_by is set
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
        if r.status_code != 200:
            fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
        api_initial = r.json().get("config", {}).get("group_by")
        if api_initial != status_col_id:
            fatal(f"API setup: config.group_by={api_initial!r}, expected {status_col_id!r}")
        print(f"[ok] API setup: config.group_by={api_initial!r} confirmed")

        # ── 5–7. UI + API pillars inside a Playwright session ─────────────────
        login_info = (
            '{"provider":"none",'
            f'"accessToken":"{token}",'
            f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
            '"role":"admin"}'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.connect(WS_URL)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            install_be_reroute(page)

            # Inject auth into localStorage before navigating to the table
            page.goto(BASE, wait_until="domcontentloaded")
            page.evaluate("(info) => localStorage.setItem('loginInfo', info)", login_info)

            goto_table(page, ws_id, TABLE_ID)

            # ── step 1: click Roadmap tab → confirm group-by selector visible ──
            try:
                roadmap_tab = page.locator('[data-testid="view-tab-Roadmap"]')
                roadmap_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_groupby_FAIL_no_tab.png")
                fatal("Roadmap tab not visible — view tabs may not have loaded")
            roadmap_tab.click()
            print("[ok] clicked Roadmap tab")

            try:
                grp_select = page.locator('[data-testid="timeline-group-by-select"]')
                grp_select.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_groupby_FAIL_no_selector.png")
                fatal("timeline-group-by-select not visible after clicking Roadmap tab")

            # UI pillar: initial group_by matches the DB value from setup
            current_val = grp_select.input_value()
            if current_val != status_col_id:
                fatal(
                    f"UI step 1: group-by shows {current_val!r}, "
                    f"expected initial {status_col_id!r}"
                )
            print(f"[ok] step 1 — UI: initial group_by={current_val!r} matches DB")

            if snapshot:
                page.screenshot(path="/output/tl_groupby_01_initial.png", full_page=True)

            # ── step 2: change group_by; wait for PUT; verify UI + API ──────────
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                page.select_option('[data-testid="timeline-group-by-select"]', category_col_id)
            print(f"[ok] selected Category ({category_col_id}) as group_by; PUT confirmed")

            # UI pillar
            ui_val = grp_select.input_value()
            if ui_val != category_col_id:
                fatal(f"UI step 2: group-by shows {ui_val!r}, expected {category_col_id!r}")
            print(f"[ok] step 2 — UI: group_by={ui_val!r}")

            if snapshot:
                page.screenshot(path="/output/tl_groupby_02_changed.png", full_page=True)

            # API pillar
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
            got_group_by = r.json().get("config", {}).get("group_by")
            if got_group_by != category_col_id:
                fatal(f"API step 2: config.group_by={got_group_by!r}, expected {category_col_id!r}")
            print(f"[ok] step 2 — API: config.group_by={got_group_by!r} confirmed in DB")

            # ── step 3: navigate away and back; verify persistence ────────────
            # goto_table waits for view-tab-Schema — no hard sleep needed.
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                roadmap_tab2 = page.locator('[data-testid="view-tab-Roadmap"]')
                roadmap_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_groupby_FAIL_no_tab_after_nav.png")
                fatal("Roadmap tab not visible after navigation back")
            roadmap_tab2.click()

            try:
                grp_select2 = page.locator('[data-testid="timeline-group-by-select"]')
                grp_select2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_groupby_FAIL_no_selector_after_nav.png")
                fatal("timeline-group-by-select not visible after navigation back")

            selected_val = grp_select2.input_value()
            if selected_val != category_col_id:
                fatal(
                    f"UI step 3 (after nav): group_by shows {selected_val!r}, "
                    f"expected {category_col_id!r}"
                )
            print("[ok] step 3 — UI: group_by persists across navigation")

            if snapshot:
                page.screenshot(path="/output/tl_groupby_03_after_nav.png", full_page=True)

            # API pillar after round-trip navigation
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view after nav: {r.status_code} {r.text[:200]}")
            got_group_by2 = r.json().get("config", {}).get("group_by")
            if got_group_by2 != category_col_id:
                fatal(
                    f"API step 3 (after nav): config.group_by={got_group_by2!r}, "
                    f"expected {category_col_id!r}"
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

    print("\n=== PASSED — e2e_test_view_timeline_groupby ===")


if __name__ == "__main__":
    main()
