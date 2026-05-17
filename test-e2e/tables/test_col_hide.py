"""E2E test: column hide/show persists across navigation in the Table view.

Scenario:
  1. Create workspace + table + 3 text columns (Alpha, Beta, Gamma) + table view.
  2. Navigate to the table page, switch to the test view.
  3. Assert all 3 columns are visible in the UI.
  4. Hide column Beta via the toolbar "Hide Fields" panel (uncheck it).
  5. Wait for PUT /views/{view_id} API response (persistence).
  6. Assert UI: Beta column header is gone; Alpha and Gamma still visible.
  7. Assert DB: view config.hidden contains Beta's column_id.
  8. Navigate away (tables list) then back; re-activate view.
  9. Assert UI: Beta still hidden after reload (persisted).
 10. Unhide Beta via toolbar "Hide Fields" panel (re-check it).
 11. Wait for PUT /views/{view_id} API response.
 12. Assert UI: all 3 columns visible again.
 13. Assert DB: view config.hidden is empty or absent.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_col_hide.py [--snapshot]
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
_TS = int(time.time())
WORKSPACE_NAME = f"colhide-{_TS}"
TABLE_ID = f"col-hide-{_TS}"
VIEW_NAME = "Hide Test View"

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
    token = r.json()["access_token"]
    print(f"[ok] login {user_name!r}")
    return token


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def get_view_config(token: str, table_id: str, view_id: int) -> dict:
    r = api("GET", f"/api/v1/tables/{table_id}/views/{view_id}", token)
    if r.status_code != 200:
        fatal(f"GET view {view_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def snap(page, name: str) -> None:
    if not SNAPSHOT:
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


def visible_col_headers(page, col_ids: list[str]) -> list[str]:
    """Return which of the given col_ids have a visible header <th>."""
    visible = []
    for cid in col_ids:
        loc = page.locator(f'[data-testid="col-header-{cid}"]')
        if loc.count() > 0 and loc.first.is_visible():
            visible.append(cid)
    return visible


def main() -> None:
    token = login(ADMIN_USER)

    # ── Setup: workspace ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    # ── Setup: table ─────────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: 3 text columns ────────────────────────────────────────────────
    col_ids = {}
    for name in ("Alpha", "Beta", "Gamma"):
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": name, "type": "text"})
        if r.status_code not in (200, 201):
            fatal(f"create column {name!r}: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
        if not col:
            fatal(f"column {name!r} not found in schema")
        col_ids[name] = col["column_id"]
        print(f"[setup] column {name!r}")

    col_a = col_ids["Alpha"]
    col_b = col_ids["Beta"]
    col_c = col_ids["Gamma"]
    print(f"[setup] col_a={col_a} col_b={col_b} col_c={col_c}")

    # ── Setup: table view ────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{TABLE_ID}/views", token,
            json={"name": VIEW_NAME, "type": "table"})
    if r.status_code not in (200, 201):
        fatal(f"create view: {r.status_code} {r.text[:200]}")
    view_schema = r.json()
    view = next((v for v in view_schema.get("views", []) if v["name"] == VIEW_NAME), None)
    if not view:
        fatal(f"view {VIEW_NAME!r} not found in schema: {view_schema.get('views')}")
    view_id = view["view_id"]
    print(f"[setup] view {VIEW_NAME!r} id={view_id}")

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

        # ── Step 1: navigate and activate the view ────────────────────────────
        wait_table_page(page, ws_name, TABLE_ID)

        tab = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible")
        tab.click()

        # Wait for Alpha column header to confirm view rendered
        try:
            page.wait_for_selector(f'[data-testid="col-header-{col_a}"]', timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_cols")
            fatal(f"Column header 'Alpha' ({col_a}) not visible within 8s")

        snap(page, "ch_01_initial")

        # ── Step 2: assert all 3 columns visible ─────────────────────────────
        vis = visible_col_headers(page, [col_a, col_b, col_c])
        if len(vis) != 3:
            fatal(f"Expected 3 visible columns, got {len(vis)}: {vis}")
        print("[ok] all 3 columns visible initially")

        # ── Step 3: hide Beta via toolbar "Hide Fields" panel ─────────────────
        hide_btn = page.locator('[data-testid="toolbar-hide-fields-btn"]')
        try:
            hide_btn.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_toolbar")
            fatal("toolbar-hide-fields-btn not visible")
        hide_btn.click()

        # Wait for the "Toggle columns" header to confirm panel rendered
        toggle_header = page.locator("text=Toggle columns")
        try:
            toggle_header.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_panel")
            fatal("Hide Fields panel did not appear")

        # Find the checkbox for Beta in the panel — label contains column name
        beta_label = page.locator("label").filter(has_text="Beta")
        try:
            beta_label.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_beta_label")
            fatal("Beta label in Hide Fields panel not visible")

        beta_checkbox = beta_label.locator("input[type='checkbox']")

        # Uncheck Beta (it should be checked = visible)
        if not beta_checkbox.is_checked():
            fatal("Beta checkbox already unchecked before we hide it")

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            beta_checkbox.click()

        snap(page, "ch_02_after_hide")

        # Close the panel by clicking the button again
        hide_btn.click()

        # ── Step 4: assert Beta hidden, Alpha+Gamma visible ────────��──────────
        # Wait for Beta column header to disappear
        try:
            page.locator(f'[data-testid="col-header-{col_b}"]').wait_for(
                state="hidden", timeout=5000
            )
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_beta_still_visible")
            fatal("Beta column header still visible after hiding")

        # Wait for Alpha to confirm table re-rendered after the config update
        try:
            page.locator(f'[data-testid="col-header-{col_a}"]').wait_for(
                state="visible", timeout=8000
            )
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_alpha_gone_after_hide")
            fatal("Alpha column header disappeared after hiding Beta")

        vis_after = visible_col_headers(page, [col_a, col_b, col_c])
        if col_b in vis_after:
            fatal(f"Beta still visible after hide: {vis_after}")
        if col_a not in vis_after or col_c not in vis_after:
            fatal(f"Alpha or Gamma missing after hiding Beta: {vis_after}")
        print("[ok] UI: Beta hidden, Alpha+Gamma visible")

        # ── Step 5: verify DB via API ─────────────────────────────────────────
        view_cfg = get_view_config(token, TABLE_ID, view_id)
        hidden_list = view_cfg.get("config", {}).get("hidden", [])
        if col_b not in hidden_list:
            fatal(f"API: config.hidden does not contain Beta ({col_b}); got {hidden_list}")
        print(f"[ok] API: config.hidden contains Beta")

        # ── Step 6: navigate away and back ────────────────────────────────────
        page.goto(f"{BASE}/tables", wait_until="domcontentloaded", timeout=15000)
        snap(page, "ch_03_away")

        wait_table_page(page, ws_name, TABLE_ID)
        tab2 = page.locator(f'[data-testid="view-tab-{VIEW_NAME}"]')
        try:
            tab2.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            fatal(f"Tab {VIEW_NAME!r} not visible after reload")
        tab2.click()

        # Wait for Alpha to confirm view loaded
        try:
            page.wait_for_selector(f'[data-testid="col-header-{col_a}"]', timeout=8000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_cols_reload")
            fatal("Alpha column header not visible after reload")

        snap(page, "ch_04_after_reload")

        # ── Step 7: assert Beta still hidden after reload ─────────────────────
        vis_reload = visible_col_headers(page, [col_a, col_b, col_c])
        if col_b in vis_reload:
            snap(page, "ch_FAIL_beta_visible_after_reload")
            fatal("Beta column visible after reload — hide not persisted")
        if col_a not in vis_reload or col_c not in vis_reload:
            fatal(f"Alpha or Gamma missing after reload: {vis_reload}")
        print("[ok] UI: Beta still hidden after navigation (persisted)")

        # ── Step 8: unhide Beta via toolbar ───────────────────────────────────
        hide_btn2 = page.locator('[data-testid="toolbar-hide-fields-btn"]')
        hide_btn2.click()

        toggle_header2 = page.locator("text=Toggle columns")
        try:
            toggle_header2.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_panel_unhide")
            fatal("Hide Fields panel did not appear for unhide")

        beta_label2 = page.locator("label").filter(has_text="Beta")
        try:
            beta_label2.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_no_beta_label_unhide")
            fatal("Beta label in Hide Fields panel not visible for unhide")

        beta_checkbox2 = beta_label2.locator("input[type='checkbox']")

        if beta_checkbox2.is_checked():
            fatal("Beta checkbox already checked — should be unchecked (hidden)")

        with page.expect_response(
            lambda r: "/api/v1/tables/" in r.url and "/views/" in r.url
                      and r.request.method == "PUT",
            timeout=10000,
        ):
            beta_checkbox2.click()

        # Close panel
        hide_btn2.click()

        snap(page, "ch_05_after_unhide")

        # ── Step 9: assert all 3 columns visible again ────────────────────────
        try:
            page.locator(f'[data-testid="col-header-{col_b}"]').wait_for(
                state="visible", timeout=5000
            )
        except PlaywrightTimeout:
            snap(page, "ch_FAIL_beta_not_back")
            fatal("Beta column header not visible after unhide")

        vis_final = visible_col_headers(page, [col_a, col_b, col_c])
        if len(vis_final) != 3:
            fatal(f"Expected 3 visible columns after unhide, got {len(vis_final)}: {vis_final}")
        print("[ok] UI: all 3 columns visible after unhide")

        # ── Step 10: verify DB — hidden empty or absent ───────────────────────
        view_cfg2 = get_view_config(token, TABLE_ID, view_id)
        hidden_list2 = view_cfg2.get("config", {}).get("hidden", [])
        if col_b in hidden_list2:
            fatal(f"API: config.hidden still contains Beta after unhide; got {hidden_list2}")
        print("[ok] API: config.hidden no longer contains Beta")

        snap(page, "ch_06_final")
        browser.close()

    # ── Teardown ──────────────────────────────────────────────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
    if r.status_code not in (200, 204):
        print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
    else:
        print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_view_table_col_hide ===")


if __name__ == "__main__":
    main()
