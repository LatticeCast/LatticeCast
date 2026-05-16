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
from playwright.sync_api import sync_playwright

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_SUFFIX = int(time.time()) % 100000
WORKSPACE_NAME = f"tl-grp-{_SUFFIX}"
TABLE_ID = f"tl-{_SUFFIX}"


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
        fatal(f"column {name!r} not found in schema; columns={[c['name'] for c in schema['columns']]}")
    return col["column_id"]


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

    # ── 2. Create blank table ────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": ws_id})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    print(f"[ok] table {TABLE_ID!r}")

    # ── 3. Add date + select columns ─────────────────────────────────────────
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

    # ── 4. Create timeline view with start/end pre-configured ────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": "Roadmap", "type": "timeline",
                  "config": {"start_col": start_col_id, "end_col": end_col_id}})
    if r.status_code != 201:
        fatal(f"create timeline view: {r.status_code} {r.text[:200]}")
    views = r.json().get("views", [])
    tl_view = next((v for v in views if v["name"] == "Roadmap"), None)
    if tl_view is None:
        fatal(f"Roadmap view not in response; views={[v['name'] for v in views]}")
    tl_view_id = tl_view["view_id"]
    print(f"[ok] timeline view 'Roadmap' → view_id={tl_view_id}")

    # ── 5 + 6 + 7. UI: set group_by, API verify, navigate + UI assert ────────
    login_info = (
        '{"provider":"none",'
        f'"accessToken":"{token}",'
        f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
        '"role":"admin"}'
    )

    with sync_playwright() as pw:
        browser = pw.chromium.connect(WS_URL)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        # Inject auth into localStorage before navigating
        page.goto(BASE, wait_until="domcontentloaded")
        page.evaluate("(info) => localStorage.setItem('loginInfo', info)", login_info)

        # Navigate to table (default view loads first)
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # Switch to Roadmap (timeline) view tab
        roadmap_tab = page.locator("button:has-text('Roadmap')").first
        roadmap_tab.wait_for(state="visible", timeout=10000)
        roadmap_tab.click()

        # Wait for the group-by selector to appear
        grp_select = page.locator('[data-testid="timeline-group-by-select"]')
        grp_select.wait_for(state="visible", timeout=10000)
        print("[ok] UI: timeline-group-by-select visible")

        # Select Status as group_by; wait for the PUT to complete
        with page.expect_response(
            lambda resp: (
                f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}" in resp.url
                and resp.request.method == "PUT"
            ),
            timeout=10000,
        ):
            page.select_option('[data-testid="timeline-group-by-select"]', status_col_id)
        print(f"[ok] UI: selected Status ({status_col_id}) as group_by; PUT confirmed")

        if snapshot:
            page.screenshot(path="/output/tl_groupby_set.png", full_page=True)

        # ── 6. API verify: group_by is in the DB ─────────────────────────────
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{tl_view_id}", token)
        if r.status_code != 200:
            fatal(f"GET view {tl_view_id}: {r.status_code} {r.text[:200]}")
        got_group_by = r.json().get("config", {}).get("group_by")
        if got_group_by != status_col_id:
            fatal(f"API: config.group_by={got_group_by!r}, expected {status_col_id!r}")
        print(f"[ok] API: config.group_by={got_group_by!r} confirmed in DB")

        # ── 7. Navigate away and back — group_by must survive ────────────────
        page.goto(f"{BASE}/{ws_id}/", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # Switch to Roadmap tab again
        roadmap_tab2 = page.locator("button:has-text('Roadmap')").first
        roadmap_tab2.wait_for(state="visible", timeout=10000)
        roadmap_tab2.click()

        grp_select2 = page.locator('[data-testid="timeline-group-by-select"]')
        grp_select2.wait_for(state="visible", timeout=10000)
        selected_val = grp_select2.input_value()
        if selected_val != status_col_id:
            fatal(
                f"UI after nav: group_by select shows {selected_val!r}, "
                f"expected {status_col_id!r}"
            )
        print("[ok] UI after nav: group_by selection persists across navigation")

        if snapshot:
            page.screenshot(path="/output/tl_groupby_after_nav.png", full_page=True)

        browser.close()

    # ── 8. Teardown: delete workspace (cascades tables + views) ─────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
    if r.status_code not in (200, 204):
        fatal(f"delete workspace: {r.status_code} {r.text[:200]}")
    print(f"[ok] deleted workspace {ws_id}")

    # Confirm workspace is gone
    listed = {w["workspace_name"] for w in api("GET", "/api/v1/workspaces", token).json()}
    if WORKSPACE_NAME in listed:
        fatal(f"workspace {WORKSPACE_NAME!r} still listed after DELETE")
    print(f"[ok] workspace no longer listed")

    print("\n=== PASSED — e2e_test_view_timeline_groupby ===")


if __name__ == "__main__":
    main()
