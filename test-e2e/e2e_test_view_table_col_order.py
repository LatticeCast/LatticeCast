"""E2E test: e2e_test_view_table_col_order — column drag-reorder persists.

Verifies that dragging a column header to a new position in the Table
(Schema) view:
  1. Updates the UI immediately (columns appear in new order).
  2. Persists to the backend via PATCH /tables/{id}/schema col_order.
  3. Survives navigation away and back.

Drag logic (handleDragReorderColumns):
    ordered.splice(fromIdx, 1); ordered.splice(toIdx, 0, fromId)
    Drag Title (idx 0) to Col C (idx 2):
        remove Title → [Col B, Col C]
        insert at 2 → [Col B, Col C, Title]

Two-container architecture (developing-e2e-test v0.8.0):
  - Connects to browser container via BROWSER_WS.
  - Hits BE through nginx via BASE_URL.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_table_col_order.py [--snapshot]
"""

from __future__ import annotations

import os
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright

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
    """Extract column names from table thead th, stripping type annotations."""
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


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. Create workspace ─────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WS_NAME!r} → {ws_id}")

    try:
        # ── 2. Create blank table ────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token,
                json={"table_id": TABLE_ID, "workspace_id": ws_id})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        title_col = next((c for c in schema["columns"] if c["name"] == "Title"), None)
        if title_col is None:
            fatal(f"blank table has no Title column; columns={[c['name'] for c in schema['columns']]}")
        title_id = title_col["column_id"]
        print(f"[ok] table {TABLE_ID!r} — Title col={title_id[:8]}…")

        # ── 3. Add two more columns so reorder is meaningful ─────────────────
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Col B", "type": "text"})
        if r.status_code != 201:
            fatal(f"add Col B: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col_b = next(c for c in schema["columns"] if c["name"] == "Col B")
        col_b_id = col_b["column_id"]
        print(f"[ok] added Col B={col_b_id[:8]}…")

        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": "Col C", "type": "text"})
        if r.status_code != 201:
            fatal(f"add Col C: {r.status_code} {r.text[:200]}")
        schema = r.json()
        col_c = next(c for c in schema["columns"] if c["name"] == "Col C")
        col_c_id = col_c["column_id"]
        print(f"[ok] added Col C={col_c_id[:8]}…")

        # API verify: initial order is [Title, Col B, Col C]
        initial_api_names = [c["name"] for c in schema["columns"]]
        if initial_api_names != ["Title", "Col B", "Col C"]:
            fatal(f"unexpected initial API col order: {initial_api_names}")
        print(f"[ok] API initial order: {initial_api_names}")

        # ── 4. UI: navigate to table on Schema (implicit) view ───────────────
        login_info = (
            '{"provider":"none",'
            f'"accessToken":"{token}",'
            f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
            '"role":"admin"}'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.connect(WS_URL)
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            # Inject auth token before navigating
            page.goto(BASE, wait_until="domcontentloaded")
            page.evaluate(
                "(info) => localStorage.setItem('loginInfo', info)", login_info,
            )
            page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
            page.wait_for_selector("table thead", timeout=12000)
            page.wait_for_timeout(500)
            snap(page, "e2e_col_order_01_initial")

            # ── 5. UI verify: initial column order ──────────────────────────
            names_before = col_names(page)
            if names_before != ["Title", "Col B", "Col C"]:
                page.screenshot(path="/output/e2e_col_order_FAIL_initial.png")
                fatal(f"UI initial order wrong: {names_before}")
            print(f"[ok] UI initial order: {names_before}")

            # ── 6. Drag Title to Col C position ─────────────────────────────
            # The <th> headers are draggable; the drag handle inside each th
            # has data-testid="col-drag-handle-{column_id}". Drag handle is
            # the grab point; drop target is the Col C <th> itself.
            title_handle = page.get_by_test_id(f"col-drag-handle-{title_id}")
            col_c_handle = page.get_by_test_id(f"col-drag-handle-{col_c_id}")

            title_handle.wait_for(state="visible", timeout=8000)
            col_c_handle.wait_for(state="visible", timeout=8000)

            title_handle.drag_to(col_c_handle)
            # Wait for PATCH /schema round-trip (reorderColumns + refreshTable)
            page.wait_for_timeout(2000)
            snap(page, "e2e_col_order_02_after_drag")

            # ── 7. UI verify: new column order after drag ────────────────────
            # Drag Title(0) to ColC(2):
            #   splice(0,1) → [Col B, Col C]
            #   splice(2,0,Title) → [Col B, Col C, Title]
            names_after = col_names(page)
            if names_after != ["Col B", "Col C", "Title"]:
                page.screenshot(path="/output/e2e_col_order_FAIL_after_drag.png")
                fatal(
                    f"UI post-drag order wrong: {names_after} "
                    "(expected ['Col B', 'Col C', 'Title'])"
                )
            print(f"[ok] UI post-drag order: {names_after}")

            # ── 8. API verify: backend persisted new col_order ───────────────
            r2 = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
            if r2.status_code != 200:
                fatal(f"GET schema after drag: {r2.status_code} {r2.text[:200]}")
            api_names_after = [c["name"] for c in r2.json()["columns"]]
            if api_names_after != ["Col B", "Col C", "Title"]:
                fatal(f"API col order wrong after drag: {api_names_after}")
            print(f"[ok] API order after drag: {api_names_after}")

            # ── 9. Navigate away then back — verify persistence ──────────────
            page.goto(f"{BASE}/{ws_id}", wait_until="networkidle")
            page.wait_for_timeout(500)
            page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="networkidle")
            page.wait_for_selector("table thead", timeout=12000)
            page.wait_for_timeout(500)
            snap(page, "e2e_col_order_03_after_nav")

            names_repersist = col_names(page)
            if names_repersist != ["Col B", "Col C", "Title"]:
                page.screenshot(path="/output/e2e_col_order_FAIL_persist.png")
                fatal(f"UI order after nav-back wrong: {names_repersist}")
            print(f"[ok] UI order persisted after navigation: {names_repersist}")

            browser.close()

    finally:
        # ── 10. Cleanup: delete workspace (cascades to tables + rows) ─────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] DELETE workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_table_col_order ===")


if __name__ == "__main__":
    main()
