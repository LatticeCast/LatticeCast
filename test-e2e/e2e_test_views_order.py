"""E2E: drag-reorder view tabs persists across reload + tables.

Covers two view-type pairs (cross-view rule):
  T1: Kanban(kanban) + Timeline(timeline) → drag Timeline before Kanban
  T2: Board(kanban) + Tbl(table)          → drag Tbl before Board

Run:
    docker compose exec test-e2e python3 /scripts/e2e_test_views_order.py [--snapshot]
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
SUFFIX = int(time.time()) % 100000
WS_NAME = f"vo-{SUFFIX}"
T1 = f"t1v{SUFFIX}"
T2 = f"t2v{SUFFIX}"
SNAP_DIR = "/output"

# View names — define once to keep assertions and drags in sync
V1A = "Kanban"    # table1 view A (created first → view_id=1)
V1B = "Timeline"  # table1 view B (created second → view_id=2)
V2A = "Board"     # table2 view A: kanban (view_id=1)
V2B = "Tbl"       # table2 view B: table type (view_id=2)


# ── Helpers ─────────────────────────────────────────────────────────────────────

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


def get_views_ordered(token: str, table_id: str) -> list[dict]:
    """GET /tables/{table_id}/views → ordered list of user views."""
    r = api("GET", f"/api/v1/tables/{table_id}/views", token)
    if r.status_code != 200:
        fatal(f"GET views {table_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def snap(page, name: str, enabled: bool) -> None:
    if enabled:
        try:
            page.screenshot(path=f"{SNAP_DIR}/{name}.png")
        except Exception:
            pass


def goto_table(page, ws_id: str, table_id: str) -> None:
    """Navigate to a table and wait for view tabs to render."""
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        fatal(f"View tabs did not load for table {table_id}")


def tab_x(page, name: str) -> float:
    """Return the left-edge x-coordinate of a view tab button."""
    loc = page.locator(f'[data-testid="view-tab-{name}"]')
    try:
        loc.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        fatal(f"Tab '{name}' not visible within 5s")
    box = loc.bounding_box()
    if not box:
        fatal(f"No bounding box for tab '{name}'")
    return box["x"]


def drag_tab(page, source_name: str, target_name: str) -> None:
    """Dispatch HTML5 drag events to reorder view tabs."""
    page.evaluate(
        """
        ([srcId, tgtId]) => {
            const srcBtn = document.querySelector(`[data-testid="${srcId}"]`);
            const tgtBtn = document.querySelector(`[data-testid="${tgtId}"]`);
            if (!srcBtn || !tgtBtn) throw new Error(`Tab not found: ${srcId} or ${tgtId}`);
            const src = srcBtn.parentElement;
            const tgt = tgtBtn.parentElement;
            const dt = new DataTransfer();
            src.dispatchEvent(new DragEvent('dragstart', {bubbles:true, cancelable:true, dataTransfer:dt}));
            tgt.dispatchEvent(new DragEvent('dragover',  {bubbles:true, cancelable:true, dataTransfer:dt}));
            tgt.dispatchEvent(new DragEvent('drop',      {bubbles:true, cancelable:true, dataTransfer:dt}));
            src.dispatchEvent(new DragEvent('dragend',   {bubbles:true}));
        }
        """,
        [f"view-tab-{source_name}", f"view-tab-{target_name}"],
    )


def wait_tab_order(page, first: str, second: str, timeout: int = 5000) -> None:
    """Wait until `first` tab appears to the left of `second` tab in the DOM."""
    try:
        page.wait_for_function(
            f"""() => {{
                const a = document.querySelector('[data-testid="view-tab-{first}"]');
                const b = document.querySelector('[data-testid="view-tab-{second}"]');
                if (!a || !b) return false;
                return a.getBoundingClientRect().x < b.getBoundingClientRect().x;
            }}""",
            timeout=timeout,
        )
    except PlaywrightTimeout:
        fatal(f"Timeout: tab '{first}' did not appear before '{second}' within {timeout}ms")


def assert_tab_order(page, first: str, second: str) -> None:
    """Assert `first` tab is to the left of `second` tab."""
    fx = tab_x(page, first)
    sx = tab_x(page, second)
    assert fx < sx, f"UI: expected tab '{first}' (x={fx:.0f}) before '{second}' (x={sx:.0f})"


def assert_api_order(token: str, table_id: str, expected: list[str]) -> None:
    """Assert GET /views returns views in the given name order."""
    views = get_views_ordered(token, table_id)
    actual = [v["name"] for v in views]
    if actual != expected:
        fatal(f"API {table_id}: expected order {expected}, got {actual}")


def setup_api(token: str) -> str:
    """Create workspace + 2 tables each with 2 user views. Returns workspace_id."""
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WS_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = str(r.json()["workspace_id"])
    print(f"[setup] workspace {WS_NAME!r} → {ws_id}")

    for tid in (T1, T2):
        r = api("POST", "/api/v1/tables", token, json={"table_id": tid, "workspace_id": ws_id})
        if r.status_code != 201:
            fatal(f"create table {tid}: {r.status_code} {r.text[:200]}")

    for name, vtype in [(V1A, "kanban"), (V1B, "timeline")]:
        r = api("POST", f"/api/v1/tables/{T1}/views", token, json={"name": name, "type": vtype})
        if r.status_code != 201:
            fatal(f"create view {name!r} on {T1}: {r.status_code} {r.text[:200]}")

    for name, vtype in [(V2A, "kanban"), (V2B, "table")]:
        r = api("POST", f"/api/v1/tables/{T2}/views", token, json={"name": name, "type": vtype})
        if r.status_code != 201:
            fatal(f"create view {name!r} on {T2}: {r.status_code} {r.text[:200]}")

    print(f"[setup] T1={T1} views=[{V1A},{V1B}]  T2={T2} views=[{V2A},{V2B}]")
    return ws_id


def teardown(token: str, ws_id: str) -> None:
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
    if r.status_code not in (200, 204):
        print(f"[warn] teardown DELETE {ws_id}: {r.status_code}", file=sys.stderr)
    else:
        print(f"[teardown] workspace {ws_id} deleted")


def main(with_snapshot: bool = False) -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    ws_id = setup_api(token)

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

        try:
            # ── step 1: initial tab order on T1 ──────────────────────────────────
            print(f"[1] T1 initial order: Schema | {V1A} | {V1B}")
            goto_table(page, ws_id, T1)
            snap(page, "step1_initial_t1", with_snapshot)

            assert_api_order(token, T1, [V1A, V1B])
            sx = tab_x(page, "Schema")
            assert sx < tab_x(page, V1A) < tab_x(page, V1B), \
                f"UI: expected Schema < {V1A} < {V1B}"
            print(f"[1] API+UI: order=Schema|{V1A}|{V1B} ✓")

            # ── step 2: drag Timeline before Kanban on T1 ────────────────────────
            print(f"[2] Drag {V1B} before {V1A} on T1")
            drag_tab(page, V1B, V1A)
            wait_tab_order(page, V1B, V1A)
            page.wait_for_load_state("networkidle", timeout=8000)
            snap(page, "step2_t1_after_drag", with_snapshot)

            assert_api_order(token, T1, [V1B, V1A])
            assert_tab_order(page, V1B, V1A)
            print(f"[2] API+UI: order=Schema|{V1B}|{V1A} ✓")

            # ── step 3: reload — order persists ──────────────────────────────────
            print(f"[3] Reload T1 — verify order persists")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(
                '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
            )
            snap(page, "step3_t1_after_reload", with_snapshot)

            assert_api_order(token, T1, [V1B, V1A])
            assert_tab_order(page, V1B, V1A)
            print(f"[3] Reload: order=Schema|{V1B}|{V1A} persists ✓")

            # ── step 4: navigate T2 → back T1, order unchanged ───────────────────
            print(f"[4] Navigate T2 → T1: verify T1 order unchanged")
            goto_table(page, ws_id, T2)
            snap(page, "step4_t2_initial", with_snapshot)

            assert_api_order(token, T2, [V2A, V2B])
            assert_tab_order(page, V2A, V2B)
            print(f"[4] T2 API+UI: order=Schema|{V2A}|{V2B} ✓")

            goto_table(page, ws_id, T1)
            snap(page, "step4_back_t1", with_snapshot)

            assert_api_order(token, T1, [V1B, V1A])
            assert_tab_order(page, V1B, V1A)
            print(f"[4] T1 after T2 nav: order=Schema|{V1B}|{V1A} unchanged ✓")

            # ── step 5: drag Tbl before Board on T2 (table+kanban types) ─────────
            print(f"[5] Navigate T2, drag {V2B} before {V2A}")
            goto_table(page, ws_id, T2)
            drag_tab(page, V2B, V2A)
            wait_tab_order(page, V2B, V2A)
            page.wait_for_load_state("networkidle", timeout=8000)
            snap(page, "step5_t2_after_drag", with_snapshot)

            assert_api_order(token, T2, [V2B, V2A])
            assert_tab_order(page, V2B, V2A)
            print(f"[5] T2 API+UI: order=Schema|{V2B}|{V2A} ✓")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(
                '[data-testid="view-tab-Schema"]', state="visible", timeout=15000
            )
            assert_api_order(token, T2, [V2B, V2A])
            assert_tab_order(page, V2B, V2A)
            print(f"[5] T2 reload: order=Schema|{V2B}|{V2A} persists ✓")

        finally:
            browser.close()

    teardown(token, ws_id)
    print("\n=== PASSED — e2e_test_views_order ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="E2E: view tab drag-reorder persists across reload + tables"
    )
    ap.add_argument("--snapshot", action="store_true", help="save per-step screenshots")
    args = ap.parse_args()
    main(with_snapshot=args.snapshot)
