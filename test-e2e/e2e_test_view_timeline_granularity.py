"""E2E test: e2e_test_view_timeline_granularity — day/week/month switch persists.

Topic: clicking a granularity button (day/week/month) in a Timeline view
persists the selection to the DB and survives navigation away + back.

Three pillars (developing-e2e-test v0.10.0):
  - Playwright UI    — click [data-testid="timeline-granularity-{g}-btn"]
  - BE API verify    — GET /api/v1/tables/{tid}/views/{vid} confirms config.granularity
  - Navigation check — navigate away and back; assert button still reflects
                       the persisted value (negative: state is not local-only)

Two-container architecture:
  - This script runs in `test-e2e` (uv image, no Chromium).
  - Connects to `browser` via BROWSER_WS for UI actions.
  - Hits the BE through nginx (BASE_URL) for setup + DB-content verification.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_timeline_granularity.py [--snapshot]
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
WORKSPACE_NAME = f"tl-gran-{_SUFFIX}"
TABLE_ID = f"tlg-{_SUFFIX}"


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


def active_granularity(page) -> str | None:
    """Return the granularity value whose button has the active (blue) class."""
    for g in ("day", "week", "month"):
        btn = page.locator(f'[data-testid="timeline-granularity-{g}-btn"]')
        cls = btn.get_attribute("class") or ""
        if "text-blue" in cls:
            return g
    return None


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

        # ── 4. Create timeline view ──────────────────────────────────────────
        # Default granularity is "month" (no explicit key in config)
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
        print(f"[ok] timeline view 'Roadmap' → view_id={tl_view_id}")

        # ── 5–7. UI + API pillars ────────────────────────────────────────────
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
                    page.screenshot(path="/output/tl_gran_FAIL_no_tab.png")
                fatal("Roadmap tab not visible")
            roadmap_tab.click()

            try:
                page.wait_for_selector(
                    '[data-testid="timeline-granularity-month-btn"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_gran_FAIL_no_btns.png")
                fatal("Granularity buttons not visible after clicking Roadmap tab")

            # UI pillar: default is "month" (active button has blue class)
            default_gran = active_granularity(page)
            if default_gran != "month":
                fatal(f"UI step 1: default granularity={default_gran!r}, expected 'month'")
            print(f"[ok] step 1 — UI: default granularity='month'")

            if snapshot:
                page.screenshot(path="/output/tl_gran_01_default.png", full_page=True)

            # ── step 2: switch to "day"; wait for PUT; verify UI + API ───────
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                page.locator('[data-testid="timeline-granularity-day-btn"]').click()
            print("[ok] clicked 'day' button; PUT confirmed")

            # UI pillar
            active_after_click = active_granularity(page)
            if active_after_click != "day":
                fatal(f"UI step 2: active granularity={active_after_click!r}, expected 'day'")
            print("[ok] step 2 — UI: granularity='day' is active")

            if snapshot:
                page.screenshot(path="/output/tl_gran_02_day.png", full_page=True)

            # API pillar
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
            got_gran = r.json().get("config", {}).get("granularity")
            if got_gran != "day":
                fatal(f"API step 2: config.granularity={got_gran!r}, expected 'day'")
            print(f"[ok] step 2 — API: config.granularity='day' confirmed in DB")

            # ── step 3: switch to "week"; wait for PUT; verify UI + API ──────
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                page.locator('[data-testid="timeline-granularity-week-btn"]').click()
            print("[ok] clicked 'week' button; PUT confirmed")

            # UI pillar
            active_week = active_granularity(page)
            if active_week != "week":
                fatal(f"UI step 3: active granularity={active_week!r}, expected 'week'")
            print("[ok] step 3 — UI: granularity='week' is active")

            if snapshot:
                page.screenshot(path="/output/tl_gran_03_week.png", full_page=True)

            # API pillar
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
            got_gran = r.json().get("config", {}).get("granularity")
            if got_gran != "week":
                fatal(f"API step 3: config.granularity={got_gran!r}, expected 'week'")
            print(f"[ok] step 3 — API: config.granularity='week' confirmed in DB")

            # ── step 4: navigate away and back; verify persistence ────────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                roadmap_tab2 = page.locator('[data-testid="view-tab-Roadmap"]')
                roadmap_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_gran_FAIL_no_tab_after_nav.png")
                fatal("Roadmap tab not visible after navigation back")
            roadmap_tab2.click()

            try:
                page.wait_for_selector(
                    '[data-testid="timeline-granularity-week-btn"]',
                    state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                if snapshot:
                    page.screenshot(path="/output/tl_gran_FAIL_no_btns_after_nav.png")
                fatal("Granularity buttons not visible after navigation back")

            # UI pillar: 'week' persisted
            active_after_nav = active_granularity(page)
            if active_after_nav != "week":
                fatal(
                    f"UI step 4 (after nav): granularity={active_after_nav!r}, "
                    f"expected 'week'"
                )
            print("[ok] step 4 — UI: granularity='week' persists across navigation")

            if snapshot:
                page.screenshot(path="/output/tl_gran_04_after_nav.png", full_page=True)

            # API pillar after round-trip navigation
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view after nav: {r.status_code} {r.text[:200]}")
            got_gran2 = r.json().get("config", {}).get("granularity")
            if got_gran2 != "week":
                fatal(
                    f"API step 4 (after nav): config.granularity={got_gran2!r}, "
                    f"expected 'week'"
                )
            print(f"[ok] step 4 — API: config.granularity='week' persisted after nav")

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

    print("\n=== PASSED — e2e_test_view_timeline_granularity ===")


if __name__ == "__main__":
    main()
