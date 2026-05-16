"""E2E smoke for the seo-bot framework — workspace + table + rows CRUD.

Models what `seo-bot` does end to end: create a clean workspace, create
the articles table, upload 3 article "files" (rows with body content),
read them back in (2, 1, 3) order to prove deterministic per-row
addressing, then tear the workspace down.

Two-container architecture (per skill developing-e2e-test v0.7.0):
  - This script runs in `test-e2e` (uv image, no Chromium).
  - It connects to the `browser` service via BROWSER_WS for UI checks.
  - It hits the BE through nginx (BASE_URL) for API actions + DB-content
    verification.

Usage:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_seo_framework.py
"""

from __future__ import annotations

import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"           # already seeded; admin role
WORKSPACE_NAME = f"seo-{int(time.time())}"
TABLE_ID = "articles"

# Three article "files" (the (2, 1, 3) set comes from re-reading in this order).
ARTICLES = [
    ("akai-spring-promo", "# akai-spring-promo\n\nPersona Akai, spring promo, ErgoPro chair."),
    ("meiwen-budget-pick", "# meiwen-budget-pick\n\nPersona Meiwen, budget pick, ErgoLite chair."),
    ("akai-bouldering", "# akai-bouldering\n\nPersona Akai, bouldering accessory bundle."),
]
READ_ORDER = (2, 1, 3)           # row_ids fetched in this sequence


def fatal(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ── BE helpers (raw requests, no SDK) ──────────────────────────────────────

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


# ── Pillars: UI (Playwright remote) + DB-via-API + (no snapshots here) ─────

def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── 1. CREATE workspace ────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws = r.json()
    ws_id = ws["workspace_id"]
    print(f"[ok] CREATE workspace {WORKSPACE_NAME!r} → {ws_id}")

    # API verify: GET /workspaces lists it
    listed = {w["workspace_name"]: w["workspace_id"]
              for w in api("GET", "/api/v1/workspaces", token).json()}
    if listed.get(WORKSPACE_NAME) != ws_id:
        fatal(f"workspace {WORKSPACE_NAME!r} not in GET /workspaces")
    print(f"[ok] GET /workspaces contains {WORKSPACE_NAME!r}")

    # ── 2. CREATE table ────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token,
            json={"table_id": TABLE_ID, "workspace_id": ws_id})
    if r.status_code != 201:
        fatal(f"create table: {r.status_code} {r.text[:200]}")
    table = r.json()
    print(f"[ok] CREATE table {TABLE_ID!r} (cols={len(table['columns'])})")

    # The blank template has a 'Title' column (text). Use it as the
    # article-name slot so we have a known column_id to write into.
    title_col_id = next(c["column_id"] for c in table["columns"] if c["name"] == "Title")

    # ── 3. UPLOAD 3 article rows ───────────────────────────────────────────
    created_row_ids: list[int] = []
    for slug, body in ARTICLES:
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {title_col_id: slug}})
        if r.status_code != 201:
            fatal(f"create row {slug!r}: {r.status_code} {r.text[:200]}")
        row = r.json()
        created_row_ids.append(row["row_id"])
        # Each row also gets a doc (markdown body uploaded to MinIO)
        d = api("PUT", f"/api/v1/tables/{TABLE_ID}/rows/{row['row_id']}/doc", token,
                data=body)
        if d.status_code not in (200, 201):
            fatal(f"upload doc for row {row['row_id']}: {d.status_code} {d.text[:200]}")
        print(f"[ok] CREATE row {row['row_id']} {slug!r} + doc ({len(body)}B)")

    # row_id is a global BE sequence — don't assume [1,2,3]. Only require
    # we got 3 distinct ascending IDs back.
    if len(set(created_row_ids)) != 3 or created_row_ids != sorted(created_row_ids):
        fatal(f"row_ids must be 3 distinct ascending values (got {created_row_ids})")

    # ── 4. READ in (2, 1, 3) order — out-of-natural-order addressing ──────
    # Map the test's index into the actual returned row_ids.
    expected_by_id = {created_row_ids[i]: ARTICLES[i] for i in range(3)}
    actual_read_order = [created_row_ids[i - 1] for i in READ_ORDER]
    for rid in actual_read_order:
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{rid}", token)
        if r.status_code != 200:
            fatal(f"GET row {rid}: {r.status_code} {r.text[:200]}")
        got_slug = r.json()["row_data"].get(title_col_id)
        want_slug = expected_by_id[rid][0]
        if got_slug != want_slug:
            fatal(f"row {rid} title: got {got_slug!r} want {want_slug!r}")
        d = api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{rid}/doc", token)
        if d.status_code != 200:
            fatal(f"GET doc {rid}: {d.status_code}")
        want_body = expected_by_id[rid][1]
        if d.text != want_body:
            fatal(f"doc {rid}: got {d.text[:80]!r} want {want_body[:80]!r}")
        print(f"[ok] READ row {rid} ({got_slug!r}) + doc match")

    # ── 5. UI assert via remote Playwright ────────────────────────────────
    login_info = (
        '{"provider":"none",'
        f'"accessToken":"{token}",'
        f'"userInfo":{{"sub":"{token}","email":"lattice@example.com","name":"lattice"}},'
        '"role":"admin"}'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.connect(WS_URL)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(BASE, wait_until="domcontentloaded")
        page.evaluate(
            "(info) => localStorage.setItem('loginInfo', info)", login_info,
        )
        page.goto(f"{BASE}/{ws_id}/{TABLE_ID}", wait_until="domcontentloaded")
        # Wait for each created row's <tr data-testid="grid-row-{rid}"> to
        # render — that's the real hydration signal. Replaces a 2000ms hard
        # sleep (see developing-e2e-test skill — banned patterns).
        for rid in created_row_ids:
            try:
                page.wait_for_selector(
                    f'[data-testid="grid-row-{rid}"]', state="visible", timeout=10000
                )
            except PlaywrightTimeout:
                page.screenshot(path="/output/e2e_seo_framework_FAIL_no_row.png", full_page=True)
                fatal(f"UI: row {rid} not rendered")
        # Each row should contain its slug as cell text.
        for rid, (slug, _) in zip(created_row_ids, ARTICLES):
            row_loc = page.locator(f'[data-testid="grid-row-{rid}"]')
            row_text = row_loc.text_content() or ""
            if slug not in row_text:
                fatal(f"UI row {rid}: slug {slug!r} not in row text {row_text!r}")
        page.screenshot(path="/output/e2e_seo_framework.png", full_page=True)
        browser.close()
    print("[ok] UI shows all 3 article rows (screenshot → .browser/e2e_seo_framework.png)")

    # ── 6. KILL workspace (cascades to tables + rows) ──────────────────────
    r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
    if r.status_code not in (200, 204):
        fatal(f"delete workspace: {r.status_code} {r.text[:200]}")
    print(f"[ok] DELETE workspace {ws_id}")

    listed_after = {w["workspace_name"] for w in api("GET", "/api/v1/workspaces", token).json()}
    if WORKSPACE_NAME in listed_after:
        fatal(f"workspace {WORKSPACE_NAME!r} still listed after DELETE")
    # Table also gone:
    r = api("GET", f"/api/v1/tables/{TABLE_ID}", token)
    if r.status_code == 200:
        fatal(f"table {TABLE_ID!r} still readable after workspace delete")
    print(f"[ok] workspace + table no longer reachable")

    print("\n=== PASSED — e2e_seo_framework ===")


if __name__ == "__main__":
    main()
