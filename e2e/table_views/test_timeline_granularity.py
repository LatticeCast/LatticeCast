"""E2E test: e2e_test_view_timeline_granularity — day/week/month switch persists.

Topic: clicking a granularity button (day/week/month) in a Timeline view
persists the selection to the DB and survives navigation away + back.

Three pillars (developing-e2e v0.10.0):
  - Playwright UI    — click [data-testid="timeline-granularity-{g}-btn"]
  - BE API verify    — GET /api/v1/tables/{tid}/views/{vid} confirms config.granularity
  - Navigation check — navigate away and back; assert button still reflects
                       the persisted value (negative: state is not local-only)

Two-container architecture:
  - This script runs in `e2e` (uv image, no Chromium).
  - Connects to `browser` via BROWSER_WS for UI actions.
  - Hits the BE through nginx (BASE_URL) for setup + DB-content verification.

Usage:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest table_views/test_timeline_granularity.py -v [--snapshot]
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, seed_login_info


SCREENSHOT_DIR = "/output"


def _col_id(schema: dict, name: str) -> str:
    col = next((c for c in schema["columns"] if c["name"] == name), None)
    if col is None:
        pytest.fail(f"column {name!r} not found; columns={[c['name'] for c in schema['columns']]}")
    return col["column_id"]


def goto_table(page, ws_id: str, table_id: str) -> None:
    """Navigate to a table and wait for view tabs to render."""
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        pytest.fail(f"View tabs did not load for table {table_id}")


def active_granularity(page) -> str | None:
    """Return the granularity value whose button has the active (blue) class."""
    for g in ("day", "week", "month"):
        btn = page.locator(f'[data-testid="timeline-granularity-{g}-btn"]')
        cls = btn.get_attribute("class") or ""
        if "text-blue" in cls:
            return g
    return None


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
    except Exception:
        pass


def test_timeline_granularity(browser, admin_token, snapshot) -> None:
    token = admin_token
    _SUFFIX = int(time.time()) % 100000
    WORKSPACE_NAME = f"tl-gran-{_SUFFIX}"
    TABLE_ID = f"tlg-{_SUFFIX}"

    print(f"[ok] login 'lattice'")

    # ── 1. Create workspace ──────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── 2. Create blank table ────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_id})
        assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
        print(f"[ok] table {TABLE_ID!r}")

        # ── 3. Add date columns ──────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Start", "type": "date"})
        assert r.status_code == 201, f"add Start col: {r.status_code} {r.text[:200]}"
        schema = r.json()
        start_col_id = _col_id(schema, "Start")
        print(f"[ok] Start col → {start_col_id}")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "End", "type": "date"})
        assert r.status_code == 201, f"add End col: {r.status_code} {r.text[:200]}"
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
        assert r.status_code == 201, f"create timeline view: {r.status_code} {r.text[:200]}"
        views = r.json().get("views", [])
        tl_view = next((v for v in views if v["name"] == "Roadmap"), None)
        if tl_view is None:
            pytest.fail(f"Roadmap view not in response; views={[v['name'] for v in views]}")
        tl_view_id = tl_view["view_id"]
        print(f"[ok] timeline view 'Roadmap' → view_id={tl_view_id}")

        # ── 5–7. UI + API pillars ────────────────────────────────────────────
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        seed_login_info(page, token, "lattice", role="admin")

        goto_table(page, ws_id, TABLE_ID)

        # ── step 1: navigate to Roadmap tab ─────────────────────────────
        try:
            roadmap_tab = page.locator('[data-testid="view-tab-Roadmap"]')
            roadmap_tab.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "tl_gran_FAIL_no_tab", snapshot)
            pytest.fail("Roadmap tab not visible")
        roadmap_tab.click()

        try:
            page.wait_for_selector(
                '[data-testid="timeline-granularity-month-btn"]',
                state="visible", timeout=10000
            )
        except PlaywrightTimeout:
            snap(page, "tl_gran_FAIL_no_btns", snapshot)
            pytest.fail("Granularity buttons not visible after clicking Roadmap tab")

        # UI pillar: default is "month" (active button has blue class)
        default_gran = active_granularity(page)
        assert default_gran == "month", \
            f"UI step 1: default granularity={default_gran!r}, expected 'month'"
        print(f"[ok] step 1 — UI: default granularity='month'")

        snap(page, "tl_gran_01_default", snapshot)

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
        assert active_after_click == "day", \
            f"UI step 2: active granularity={active_after_click!r}, expected 'day'"
        print("[ok] step 2 — UI: granularity='day' is active")

        snap(page, "tl_gran_02_day", snapshot)

        # API pillar
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
        assert r.status_code == 200, \
            f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}"
        got_gran = r.json().get("config", {}).get("granularity")
        assert got_gran == "day", \
            f"API step 2: config.granularity={got_gran!r}, expected 'day'"
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
        assert active_week == "week", \
            f"UI step 3: active granularity={active_week!r}, expected 'week'"
        print("[ok] step 3 — UI: granularity='week' is active")

        snap(page, "tl_gran_03_week", snapshot)

        # API pillar
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
        assert r.status_code == 200, \
            f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}"
        got_gran = r.json().get("config", {}).get("granularity")
        assert got_gran == "week", \
            f"API step 3: config.granularity={got_gran!r}, expected 'week'"
        print(f"[ok] step 3 — API: config.granularity='week' confirmed in DB")

        # ── step 4: navigate away and back; verify persistence ────────────
        page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
        goto_table(page, ws_id, TABLE_ID)

        try:
            roadmap_tab2 = page.locator('[data-testid="view-tab-Roadmap"]')
            roadmap_tab2.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            snap(page, "tl_gran_FAIL_no_tab_after_nav", snapshot)
            pytest.fail("Roadmap tab not visible after navigation back")
        roadmap_tab2.click()

        try:
            page.wait_for_selector(
                '[data-testid="timeline-granularity-week-btn"]',
                state="visible", timeout=10000
            )
        except PlaywrightTimeout:
            snap(page, "tl_gran_FAIL_no_btns_after_nav", snapshot)
            pytest.fail("Granularity buttons not visible after navigation back")

        # UI pillar: 'week' persisted
        active_after_nav = active_granularity(page)
        assert active_after_nav == "week", \
            f"UI step 4 (after nav): granularity={active_after_nav!r}, expected 'week'"
        print("[ok] step 4 — UI: granularity='week' persists across navigation")

        snap(page, "tl_gran_04_after_nav", snapshot)

        # API pillar after round-trip navigation
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
        assert r.status_code == 200, \
            f"GET view after nav: {r.status_code} {r.text[:200]}"
        got_gran2 = r.json().get("config", {}).get("granularity")
        assert got_gran2 == "week", \
            f"API step 4 (after nav): config.granularity={got_gran2!r}, expected 'week'"
        print(f"[ok] step 4 — API: config.granularity='week' persisted after nav")

        page.close()

    finally:
        # ── Teardown: delete workspace (cascades tables + views) ──────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}")
        else:
            listed = {w["workspace_name"] for w in api("GET", "/api/v1/workspaces", token).json()}
            if WORKSPACE_NAME in listed:
                print(f"WARN: workspace {WORKSPACE_NAME!r} still listed after DELETE")
            else:
                print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_timeline_granularity ===")
