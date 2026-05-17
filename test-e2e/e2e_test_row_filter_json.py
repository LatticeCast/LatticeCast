#!/usr/bin/env python3
"""E2E test: filter_json query parameter on GET /tables/{table_id}/rows.

Scenario:
  1. Create workspace + table + 2 text columns (City, Status) + 4 rows.
  2. Navigate to table page — verify all 4 rows visible (UI pillar).
  3. API: GET rows?filter_json={"col_status":"active"} → only matching rows.
  4. API: GET rows?filter_json={"col_city":"Tokyo"} → single match.
  5. API: GET rows?filter_json={"col_city":"Tokyo","col_status":"active"} → AND.
  6. API: GET rows?filter_json={"col_status":"nonexistent"} → empty result.
  7. API: GET rows?filter_json={} → returns all rows (no filter).
  8. API: GET rows?filter_json=invalid → returns all rows (bad JSON fallback).
  9. Teardown.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_row_filter_json.py [--snapshot]
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = os.environ["BASE_URL"].rstrip("/")
WS_URL = os.environ["BROWSER_WS"]
ADMIN_USER = "lattice"
_TS = int(time.time()) % 100000
WORKSPACE_NAME = f"filtjson-{_TS}"
TABLE_ID = f"filtjson-{_TS}"

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


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def main() -> None:
    token = login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: workspace ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_data = r.json()
    ws_uuid = str(ws_data["workspace_id"])
    ws_name = ws_data["workspace_name"]
    print(f"[setup] workspace {ws_name!r} → id={ws_uuid}")

    try:
        # ── Setup: table ─────────────────────────────────────────────────────
        r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
        if r.status_code != 201:
            fatal(f"create table: {r.status_code} {r.text[:200]}")
        print(f"[setup] table {TABLE_ID!r}")

        # ── Setup: 2 text columns (City, Status) ────────────────────────────
        col_ids = {}
        for name in ("City", "Status"):
            r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                    json={"name": name, "type": "text"})
            if r.status_code not in (200, 201):
                fatal(f"create column {name!r}: {r.status_code} {r.text[:200]}")
            schema = r.json()
            col = next((c for c in schema.get("columns", []) if c["name"] == name), None)
            if not col:
                fatal(f"column {name!r} not found in schema")
            col_ids[name] = col["column_id"]
            print(f"[setup] column {name!r} → {col_ids[name]}")

        col_city = col_ids["City"]
        col_status = col_ids["Status"]

        # ── Setup: 4 rows ────────────────────────────────────────────────────
        rows_spec = [
            {"City": "Tokyo", "Status": "active"},
            {"City": "London", "Status": "inactive"},
            {"City": "Paris", "Status": "active"},
            {"City": "Berlin", "Status": "inactive"},
        ]
        row_ids: list[int] = []
        for spec in rows_spec:
            row_data = {col_city: spec["City"], col_status: spec["Status"]}
            r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                    json={"row_data": row_data})
            if r.status_code != 201:
                fatal(f"create row {spec!r}: {r.status_code} {r.text[:200]}")
            row_ids.append(r.json()["row_id"])
        print(f"[setup] rows: {row_ids}")

        rid_tokyo, rid_london, rid_paris, rid_berlin = row_ids

        # ── UI Pillar: verify all rows visible ───────────────────────────────
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

            page.goto(f"{BASE}/{ws_name}/{TABLE_ID}", wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
            except PlaywrightTimeout:
                fatal("Table page did not finish loading")

            for rid in row_ids:
                loc = page.locator(f'[data-testid="grid-row-{rid}"]')
                try:
                    loc.wait_for(state="visible", timeout=8000)
                except PlaywrightTimeout:
                    snap(page, "fjson_FAIL_row_not_visible")
                    fatal(f"Row {rid} not visible in grid")

            snap(page, "fjson_01_all_rows_visible")
            print("[ok] UI: all 4 rows visible in table grid")
            browser.close()

        # ── API Pillar: filter_json queries ──────────────────────────────────

        # Test 1: filter by Status=active → Tokyo, Paris
        fj = json.dumps({col_status: "active"})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json status=active: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        expected = {rid_tokyo, rid_paris}
        if result_ids != expected:
            fatal(f"filter Status=active: expected {expected}, got {result_ids}")
        print("[ok] API: filter_json Status=active → Tokyo, Paris")

        # Test 2: filter by City=Tokyo → single row
        fj = json.dumps({col_city: "Tokyo"})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json city=Tokyo: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if result_ids != {rid_tokyo}:
            fatal(f"filter City=Tokyo: expected {{{rid_tokyo}}}, got {result_ids}")
        print("[ok] API: filter_json City=Tokyo → single row")

        # Test 3: multi-column AND — City=Tokyo AND Status=active
        fj = json.dumps({col_city: "Tokyo", col_status: "active"})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json city+status: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if result_ids != {rid_tokyo}:
            fatal(f"filter City=Tokyo+Status=active: expected {{{rid_tokyo}}}, got {result_ids}")
        print("[ok] API: filter_json City=Tokyo AND Status=active → Tokyo only")

        # Test 4: multi-column AND with no match — City=Tokyo AND Status=inactive
        fj = json.dumps({col_city: "Tokyo", col_status: "inactive"})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json city=Tokyo+status=inactive: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if result_ids != set():
            fatal(f"filter City=Tokyo+Status=inactive: expected empty, got {result_ids}")
        print("[ok] API: filter_json City=Tokyo AND Status=inactive → empty")

        # Test 5: no match at all
        fj = json.dumps({col_status: "nonexistent"})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json nonexistent: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if result_ids != set():
            fatal(f"filter nonexistent: expected empty, got {result_ids}")
        print("[ok] API: filter_json nonexistent value → empty")

        # Test 6: empty object filter → returns all rows
        fj = json.dumps({})
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
        if r.status_code != 200:
            fatal(f"filter_json empty obj: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if not result_ids.issuperset(set(row_ids)):
            fatal(f"filter empty obj: expected all rows {set(row_ids)}, got {result_ids}")
        print("[ok] API: filter_json empty object → all rows returned")

        # Test 7: invalid JSON → fallback returns all rows
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json=not-valid-json", token)
        if r.status_code != 200:
            fatal(f"filter_json invalid: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if not result_ids.issuperset(set(row_ids)):
            fatal(f"filter invalid json: expected all rows {set(row_ids)}, got {result_ids}")
        print("[ok] API: filter_json invalid JSON → graceful fallback, all rows returned")

        # Test 8: no filter_json param → returns all rows
        r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows", token)
        if r.status_code != 200:
            fatal(f"no filter_json: {r.status_code} {r.text[:200]}")
        result_ids = {row["row_id"] for row in r.json()}
        if not result_ids.issuperset(set(row_ids)):
            fatal(f"no filter_json: expected all rows {set(row_ids)}, got {result_ids}")
        print("[ok] API: no filter_json → all rows returned")

    finally:
        # ── Teardown ─────────────────────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_uuid}", token)
        if r.status_code not in (200, 204):
            print(f"warn: delete workspace returned {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] DELETE workspace {ws_uuid}")

    print("\n=== PASSED — e2e_test_row_filter_json ===")


if __name__ == "__main__":
    main()
