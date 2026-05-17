"""E2E test: delete view — view_order updated, default_view fallback, active-view fallback.

Covers three delete scenarios:
  1. Delete a non-active, non-default view (Timeline View) →
       tab disappears; view_order no longer contains its ID.
  2. Delete the default_view (Kanban View) →
       tab disappears; API returns default_view=null.
  3. Delete the currently active view (Table View) →
       tab disappears; FE falls back to the implicit Schema view
       (data-active-view-id=0).

Two-container architecture (developing-e2e-test):
  - Runs in test-e2e container (no Chromium).
  - Playwright connects to browser service via BROWSER_WS.
  - API checks hit BE through BASE_URL.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_views_delete.py [--snapshot]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time())
WORKSPACE_NAME = f"vdel-{_TS}"
TABLE_ID = f"views-del-{_TS}"

TABLE_VIEW_NAME = "Table View"
KANBAN_VIEW_NAME = "Kanban View"
TIMELINE_VIEW_NAME = "Timeline View"
SCHEMA_VIEW_ID = 0  # implicit table view (view_id=0, name="Schema")


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
    token = r.json()["access_token"]
    print(f"[ok] login {user_name!r}")
    return token


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def get_schema(token: str, table_id: str) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    if r.status_code != 200:
        fatal(f"GET /tables/{table_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def snap(page, name: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def wait_table_page(page, ws_name: str, table_id: str) -> None:
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    except PlaywrightTimeout:
        fatal(f"Table page did not finish loading for {table_id!r}")


def assert_tab_visible(page, tab_name: str) -> None:
    try:
        page.locator(f'[data-testid="view-tab-{tab_name}"]').wait_for(
            state="visible", timeout=8000
        )
    except PlaywrightTimeout:
        fatal(f"Tab {tab_name!r} not visible within 8s")
    print(f"[ok] UI: tab {tab_name!r} visible")


def assert_tab_gone(page, tab_name: str) -> None:
    try:
        page.locator(f'[data-testid="view-tab-{tab_name}"]').wait_for(
            state="hidden", timeout=8000
        )
    except PlaywrightTimeout:
        fatal(f"Tab {tab_name!r} still visible 8s after deletion")
    print(f"[ok] UI: tab {tab_name!r} gone")


def delete_view_via_ui(page, view_name: str) -> None:
    """Hover the view tab to reveal the delete button, click it, wait for DELETE response."""
    tab = page.locator(f'[data-testid="view-tab-{view_name}"]')
    tab.wait_for(state="visible", timeout=5000)
    tab.hover()
    delete_btn = page.locator(f'[data-testid="view-tab-delete-{view_name}"]')
    with page.expect_response(
        lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                  and r.request.method == "DELETE"
    ) as resp_info:
        delete_btn.click()
    if not resp_info.value.ok:
        fatal(f"DELETE view {view_name!r} returned {resp_info.value.status}")
    print(f"[ok] UI: delete action for {view_name!r} — API responded {resp_info.value.status}")


def assert_active_view_id(page, expected_id: int) -> None:
    """Check data-active-view-id attribute on the ViewSwitcher outer div."""
    try:
        page.wait_for_selector(
            f'[data-active-view-id="{expected_id}"]', timeout=5000
        )
    except PlaywrightTimeout:
        actual = page.locator('[data-active-view-id]').get_attribute("data-active-view-id")
        fatal(f"Active view: expected id={expected_id}, got {actual!r}")
    print(f"[ok] UI: active view id={expected_id}")


def main(snapshot: bool = False) -> None:
    token = login(ADMIN_USER)

    # ── Setup: workspace ──────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    # ── Setup: table ──────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: 3 views ────────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": TABLE_VIEW_NAME, "type": "table"})
    if r.status_code not in (200, 201):
        fatal(f"create table view: {r.status_code} {r.text[:200]}")
    schema = r.json()
    table_view = next((v for v in schema.get("views", []) if v["name"] == TABLE_VIEW_NAME), None)
    if not table_view:
        fatal(f"table view not found in response; views={schema.get('views')}")
    table_view_id = table_view["view_id"]
    print(f"[setup] {TABLE_VIEW_NAME!r} id={table_view_id}")

    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": KANBAN_VIEW_NAME, "type": "kanban"})
    if r.status_code not in (200, 201):
        fatal(f"create kanban view: {r.status_code} {r.text[:200]}")
    schema = r.json()
    kanban_view = next((v for v in schema.get("views", []) if v["name"] == KANBAN_VIEW_NAME), None)
    if not kanban_view:
        fatal(f"kanban view not found in response; views={schema.get('views')}")
    kanban_view_id = kanban_view["view_id"]
    print(f"[setup] {KANBAN_VIEW_NAME!r} id={kanban_view_id}")

    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": TIMELINE_VIEW_NAME, "type": "timeline"})
    if r.status_code not in (200, 201):
        fatal(f"create timeline view: {r.status_code} {r.text[:200]}")
    schema = r.json()
    timeline_view = next((v for v in schema.get("views", []) if v["name"] == TIMELINE_VIEW_NAME), None)
    if not timeline_view:
        fatal(f"timeline view not found; views={schema.get('views')}")
    timeline_view_id = timeline_view["view_id"]
    print(f"[setup] {TIMELINE_VIEW_NAME!r} id={timeline_view_id}")

    # ── Setup: set Kanban View as default_view ─────────────────────────────────
    r = api("PATCH", f"/api/v1/tables/{TABLE_ID}/schema", token,
            json={"default_view": kanban_view_id})
    if r.status_code != 200:
        fatal(f"set default_view: {r.status_code} {r.text[:200]}")
    print(f"[setup] default_view={kanban_view_id} ({KANBAN_VIEW_NAME!r})")

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

        wait_table_page(page, ws_name, TABLE_ID)
        print("[ok] navigated to table page")
        snap(page, "vd_01_initial", snapshot)

        # ── Step 1: verify initial state ──────────────────────────────────────
        for tab_name in [TABLE_VIEW_NAME, KANBAN_VIEW_NAME, TIMELINE_VIEW_NAME]:
            assert_tab_visible(page, tab_name)

        initial = get_schema(token, TABLE_ID)
        for vid in [table_view_id, kanban_view_id, timeline_view_id]:
            if vid not in initial["view_order"]:
                fatal(f"API: view_id={vid} missing from initial view_order={initial['view_order']}")
        if initial.get("default_view") != kanban_view_id:
            fatal(f"API: expected default_view={kanban_view_id}, got {initial.get('default_view')}")
        print(f"[ok] API: initial state — view_order={initial['view_order']} default_view={initial['default_view']}")

        # ── Step 2: delete Timeline View (non-active, non-default) ────────────
        delete_view_via_ui(page, TIMELINE_VIEW_NAME)
        assert_tab_gone(page, TIMELINE_VIEW_NAME)
        snap(page, "vd_02_timeline_deleted", snapshot)

        schema2 = get_schema(token, TABLE_ID)
        view_names2 = [v["name"] for v in schema2.get("views", [])]
        if TIMELINE_VIEW_NAME in view_names2:
            fatal(f"API: {TIMELINE_VIEW_NAME!r} still in views after deletion: {view_names2}")
        if timeline_view_id in schema2.get("view_order", []):
            fatal(f"API: timeline_view_id={timeline_view_id} still in view_order={schema2['view_order']}")
        print(f"[ok] API: {TIMELINE_VIEW_NAME!r} gone — view_order={schema2['view_order']}")

        # default_view unchanged (was kanban, not timeline)
        if schema2.get("default_view") != kanban_view_id:
            fatal(f"API: default_view changed unexpectedly after deleting non-default view; got {schema2.get('default_view')}")
        print(f"[ok] API: default_view={kanban_view_id} unchanged after non-default deletion")

        # ── Step 3: delete Kanban View (the default_view) ─────────────────────
        delete_view_via_ui(page, KANBAN_VIEW_NAME)
        assert_tab_gone(page, KANBAN_VIEW_NAME)
        snap(page, "vd_03_kanban_deleted", snapshot)

        schema3 = get_schema(token, TABLE_ID)
        view_names3 = [v["name"] for v in schema3.get("views", [])]
        if KANBAN_VIEW_NAME in view_names3:
            fatal(f"API: {KANBAN_VIEW_NAME!r} still in views after deletion: {view_names3}")
        if kanban_view_id in schema3.get("view_order", []):
            fatal(f"API: kanban_view_id={kanban_view_id} still in view_order={schema3['view_order']}")
        if schema3.get("default_view") is not None:
            fatal(f"API: expected default_view=null after deleting default view; got {schema3.get('default_view')}")
        print(f"[ok] API: {KANBAN_VIEW_NAME!r} gone — default_view cleared to null")

        # ── Step 4: click Table View to make it active, then delete ───────────
        tab_btn = page.locator(f'[data-testid="view-tab-{TABLE_VIEW_NAME}"]')
        tab_btn.wait_for(state="visible", timeout=5000)
        tab_btn.click()
        assert_active_view_id(page, table_view_id)
        print(f"[ok] UI: {TABLE_VIEW_NAME!r} tab is now active (id={table_view_id})")
        snap(page, "vd_04_table_active", snapshot)

        delete_view_via_ui(page, TABLE_VIEW_NAME)
        assert_tab_gone(page, TABLE_VIEW_NAME)
        snap(page, "vd_05_table_deleted", snapshot)

        # FE must fall back to Schema (view_id=0)
        assert_active_view_id(page, SCHEMA_VIEW_ID)
        print(f"[ok] UI: active view fell back to Schema (id={SCHEMA_VIEW_ID})")

        # Schema tab is always visible (implicit view)
        assert_tab_visible(page, "Schema")

        schema4 = get_schema(token, TABLE_ID)
        if schema4.get("views"):
            fatal(f"API: expected empty views after deleting all user views; got {schema4['views']}")
        if schema4.get("view_order"):
            fatal(f"API: expected empty view_order after deleting all user views; got {schema4['view_order']}")
        print(f"[ok] API: all user views deleted — views=[] view_order=[]")

        snap(page, "vd_06_final", snapshot)
        browser.close()

    # ── Teardown ──────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_views_delete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true", help="Capture screenshots at each step")
    args = parser.parse_args()
    main(snapshot=args.snapshot)
