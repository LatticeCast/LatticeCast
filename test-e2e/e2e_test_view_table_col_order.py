"""E2E test: e2e_test_view_table_col_order — column drag-reorder persists.

Verifies that dragging a column header to a new position in the Table view:
  1. Updates the UI immediately (columns appear in new order).
  2. Persists to the backend via PATCH /tables/{id}/schema col_order.
  3. Survives navigation away and back.

Drag: Title column (first) → Col C position (last).
Expected: Title moves to the end, after Col C.

Run:
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_col_order.py [--snapshot]
"""

from __future__ import annotations

import os
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time())
WS_NAME = f"e2e-col-ord-{_TS}"
TABLE_ID = f"col-ord-{_TS}"


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
    return r.json()["access_token"]


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    return requests.request(
        method, f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15, **kw,
    )


def col_names(page) -> list[str]:
    """Read visible column names from table thead, stripping type suffix."""
    names = []
    for th in page.locator("table thead th").all():
        text = (th.text_content() or "").strip()
        col = re.sub(r"\s*\(\w+\)\s*$", "", text).strip()
        if col and col != "#":
            names.append(col)
    return names


def snap(page, name: str) -> None:
    if SNAPSHOT:
        page.screenshot(path=f"/output/{name}.png", full_page=True)


def goto_table(page, ws_id: str, table_id: str) -> None:
    """Navigate to table and wait for view tabs to render."""
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

    # ── 1. Create workspace ────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WS_NAME!r} → {ws_id}")

    try:
        # ── 2. Create blank table ──────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_id})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        title_col = next((c for c in schema["columns"] if c["name"] == "Title"), None)
        if title_col is None:
            fatal(f"blank table has no Title column; got {[c['name'] for c in schema['columns']]}")
        title_id = title_col["column_id"]
        print(f"[ok] table {TABLE_ID!r} — Title col={title_id[:8]}…")

        # ── 3. Add two more columns ────────────────────────────────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Col B", "type": "text"})
        if r.status_code != 201:
            fatal(f"add Col B: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col_b_id = next(c["column_id"] for c in schema["columns"] if c["name"] == "Col B")
        print(f"[ok] added Col B={col_b_id[:8]}…")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Col C", "type": "text"})
        if r.status_code != 201:
            fatal(f"add Col C: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col_c_id = next(c["column_id"] for c in schema["columns"] if c["name"] == "Col C")
        print(f"[ok] added Col C={col_c_id[:8]}…")

        # ── 4. API verify: get current order from fresh GET ────────────────────
        r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
        if r.status_code != 200:
            fatal(f"GET schema: {r.status_code} {r.text[:200]}")
        initial_cols = r.json()["columns"]
        initial_names = [c["name"] for c in initial_cols]
        for expected in ("Title", "Col B", "Col C"):
            if expected not in initial_names:
                fatal(f"column {expected!r} missing from initial schema; got {initial_names}")
        print(f"[ok] API initial order: {initial_names}")

        # Compute expected order after dragging Title → Col C position
        # handleDragReorderColumns: splice(fromIdx,1) then splice(toIdx,0,fromId)
        initial_ids = [c["column_id"] for c in initial_cols]
        from_idx = initial_ids.index(title_id)
        to_idx = initial_ids.index(col_c_id)
        expected_ids = initial_ids[:]
        del expected_ids[from_idx]
        expected_ids.insert(to_idx, title_id)
        expected_names = []
        id_to_name = {c["column_id"]: c["name"] for c in initial_cols}
        for cid in expected_ids:
            expected_names.append(id_to_name[cid])
        print(f"[ok] expected post-drag order: {expected_names}")

        # ── 5. Browser: auth inject + route rewrite + navigate ─────────────────
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
            snap(page, "e2e_col_order_01_initial")

            # ── 6. Wait for table grid to render ──────────────────────────────
            try:
                page.wait_for_selector("table thead", timeout=15000)
            except PlaywrightTimeout:
                page.screenshot(path="/output/e2e_col_order_FAIL_no_table.png")
                fatal("table thead not visible — table grid did not render")

            # Wait for column drag handles to appear
            try:
                page.wait_for_selector(
                    f'[data-testid="col-drag-handle-{title_id}"]', timeout=8000
                )
                page.wait_for_selector(
                    f'[data-testid="col-drag-handle-{col_c_id}"]', timeout=8000
                )
            except PlaywrightTimeout:
                page.screenshot(path="/output/e2e_col_order_FAIL_no_handles.png")
                fatal("Column drag handles not found — columns may not have loaded")

            # ── 7. UI verify: initial column order ────────────────────────────
            names_before = col_names(page)
            if "Title" not in names_before:
                page.screenshot(path="/output/e2e_col_order_FAIL_initial.png")
                fatal(f"Title column missing from UI; got {names_before}")
            print(f"[ok] UI initial order: {names_before}")

            # ── 8. Drag Title column → Col C position ─────────────────────────
            # Target the <th draggable="true"> elements — drag events are on the
            # <th>, the data-testid span is just a visual grab handle inside it.
            src_sel = f'th[draggable="true"]:has([data-testid="col-drag-handle-{title_id}"])'
            tgt_sel = f'th[draggable="true"]:has([data-testid="col-drag-handle-{col_c_id}"])'

            # Wait for the PATCH /schema to land BEFORE moving on. Replaces a
            # 1500ms hard wait — see developing-e2e-test skill banned-pattern
            # rule. The FE issues PATCH after drag; we must observe it.
            with page.expect_response(
                lambda r: r.request.method == "PATCH"
                          and r.url.rstrip("/").endswith(f"/api/v1/tables/{TABLE_ID}/schema")
                          and r.ok,
                timeout=10000,
            ):
                page.drag_and_drop(src_sel, tgt_sel)
            snap(page, "e2e_col_order_02_after_drag")

            # ── 9. UI reflects new order ──────────────────────────────────────
            title_after_colc_js = """() => {
                const ths = Array.from(document.querySelectorAll('table thead th'));
                const names = ths
                    .map(th => th.textContent.trim().replace(/\\s*\\(\\w+\\)\\s*$/, '').trim())
                    .filter(n => n && n !== '#');
                const ti = names.indexOf('Title');
                const ci = names.indexOf('Col C');
                return ti !== -1 && ci !== -1 && ti > ci;
            }"""
            try:
                page.wait_for_function(title_after_colc_js, timeout=8000)
            except PlaywrightTimeout:
                names_fail = col_names(page)
                page.screenshot(path="/output/e2e_col_order_FAIL_after_drag.png")
                fatal(
                    f"UI post-drag: Title did not move after Col C; got {names_fail}. "
                    "Expected Title after Col C."
                )

            names_after = col_names(page)
            ti = names_after.index("Title")
            ci = names_after.index("Col C")
            if ti <= ci:
                page.screenshot(path="/output/e2e_col_order_FAIL_after_drag.png")
                fatal(f"UI post-drag order wrong: Title(idx={ti}) not after Col C(idx={ci}); got {names_after}")
            print(f"[ok] UI post-drag order: {names_after}")

            # ── 10. API verify: backend persisted new col_order ───────────────
            # PATCH already awaited via expect_response above; can GET safely.
            r2 = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r2.status_code != 200:
                fatal(f"GET schema after drag: {r2.status_code} {r2.text[:200]}")
            api_cols_after = r2.json()["columns"]
            api_names_after = [c["name"] for c in api_cols_after]
            if "Title" not in api_names_after or "Col C" not in api_names_after:
                fatal(f"API missing columns after drag: {api_names_after}")
            if api_names_after.index("Title") <= api_names_after.index("Col C"):
                fatal(f"API col order wrong after drag: Title should be after Col C; got {api_names_after}")
            print(f"[ok] API order after drag: {api_names_after}")

            # ── 11. Navigate away then back — verify persistence ───────────────
            # Navigate to workspace root (away) then back to table. goto_table
            # waits for view-tab-Schema to be visible (hydration signal); we
            # then wait for the column drag-handles to be present, which is
            # the real "table grid hydrated" signal.
            page.goto(f"{BASE}/{ws_id}", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)
            try:
                page.wait_for_selector("table thead", timeout=15000)
                page.wait_for_selector(
                    f'[data-testid="col-drag-handle-{title_id}"]', timeout=8000
                )
            except PlaywrightTimeout:
                page.screenshot(path="/output/e2e_col_order_FAIL_persist_no_table.png")
                fatal("Table did not render / hydrate after navigation back")
            snap(page, "e2e_col_order_03_after_nav")

            names_repersist = col_names(page)
            if "Title" not in names_repersist or "Col C" not in names_repersist:
                fatal(f"Columns missing after nav-back: {names_repersist}")
            if names_repersist.index("Title") <= names_repersist.index("Col C"):
                page.screenshot(path="/output/e2e_col_order_FAIL_persist.png")
                fatal(f"UI order after nav-back: Title should be after Col C; got {names_repersist}")
            print(f"[ok] UI order persisted after navigation: {names_repersist}")

            browser.close()

    finally:
        # ── Cleanup ────────────────────────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] DELETE workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_table_col_order ===")


if __name__ == "__main__":
    main()
