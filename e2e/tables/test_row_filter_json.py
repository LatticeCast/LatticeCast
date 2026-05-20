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
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest tables/test_row_filter_json.py -v [--snapshot]
"""

from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, seed_login_info


_TS = int(time.time()) % 100000
TABLE_ID = f"filtjson-{_TS}"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def test_row_filter_json(browser, admin_token, workspace, snapshot):
    token = admin_token
    ws_id, ws_name = workspace
    print(f"[ok] login admin")

    print(f"[setup] workspace {ws_name!r} → id={ws_id}")

    # ── Setup: table ─────────────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": TABLE_ID, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[setup] table {TABLE_ID!r}")

    # ── Setup: 2 text columns (City, Status) ────────────────────────────
    col_ids = {}
    for col_name in ("City", "Status"):
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/columns", token,
                json={"name": col_name, "type": "text"})
        assert r.status_code in (200, 201), f"create column {col_name!r}: {r.status_code} {r.text[:200]}"
        schema = r.json()
        col = next((c for c in schema.get("columns", []) if c["name"] == col_name), None)
        assert col, f"column {col_name!r} not found in schema"
        col_ids[col_name] = col["column_id"]
        print(f"[setup] column {col_name!r} → {col_ids[col_name]}")

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
        assert r.status_code == 201, f"create row {spec!r}: {r.status_code} {r.text[:200]}"
        row_ids.append(r.json()["row_id"])
    print(f"[setup] rows: {row_ids}")

    rid_tokyo, rid_london, rid_paris, rid_berlin = row_ids

    # ── UI Pillar: verify all rows visible ───────────────────────────────
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    seed_login_info(page, token, "lattice", role="admin")
    try:
        page.goto(f"{BASE}/{ws_name}/{TABLE_ID}", wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
        except PlaywrightTimeout:
            pytest.fail("Table page did not finish loading")

        for rid in row_ids:
            loc = page.locator(f'[data-testid="grid-row-{rid}"]')
            try:
                loc.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeout:
                snap(page, "fjson_FAIL_row_not_visible", snapshot)
                pytest.fail(f"Row {rid} not visible in grid")

        snap(page, "fjson_01_all_rows_visible", snapshot)
        print("[ok] UI: all 4 rows visible in table grid")
    finally:
        page.close()

    # ── API Pillar: filter_json queries ──────────────────────────────────

    # Test 1: filter by Status=active → Tokyo, Paris
    fj = json.dumps({col_status: "active"})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json status=active: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    expected = {rid_tokyo, rid_paris}
    assert result_ids == expected, f"filter Status=active: expected {expected}, got {result_ids}"
    print("[ok] API: filter_json Status=active → Tokyo, Paris")

    # Test 2: filter by City=Tokyo → single row
    fj = json.dumps({col_city: "Tokyo"})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json city=Tokyo: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids == {rid_tokyo}, f"filter City=Tokyo: expected {{{rid_tokyo}}}, got {result_ids}"
    print("[ok] API: filter_json City=Tokyo → single row")

    # Test 3: multi-column AND — City=Tokyo AND Status=active
    fj = json.dumps({col_city: "Tokyo", col_status: "active"})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json city+status: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids == {rid_tokyo}, f"filter City=Tokyo+Status=active: expected {{{rid_tokyo}}}, got {result_ids}"
    print("[ok] API: filter_json City=Tokyo AND Status=active → Tokyo only")

    # Test 4: multi-column AND with no match — City=Tokyo AND Status=inactive
    fj = json.dumps({col_city: "Tokyo", col_status: "inactive"})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json city=Tokyo+status=inactive: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids == set(), f"filter City=Tokyo+Status=inactive: expected empty, got {result_ids}"
    print("[ok] API: filter_json City=Tokyo AND Status=inactive → empty")

    # Test 5: no match at all
    fj = json.dumps({col_status: "nonexistent"})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json nonexistent: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids == set(), f"filter nonexistent: expected empty, got {result_ids}"
    print("[ok] API: filter_json nonexistent value → empty")

    # Test 6: empty object filter → returns all rows
    fj = json.dumps({})
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json={fj}", token)
    assert r.status_code == 200, f"filter_json empty obj: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids.issuperset(set(row_ids)), f"filter empty obj: expected all rows {set(row_ids)}, got {result_ids}"
    print("[ok] API: filter_json empty object → all rows returned")

    # Test 7: invalid JSON → fallback returns all rows
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows?filter_json=not-valid-json", token)
    assert r.status_code == 200, f"filter_json invalid: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids.issuperset(set(row_ids)), f"filter invalid json: expected all rows {set(row_ids)}, got {result_ids}"
    print("[ok] API: filter_json invalid JSON → graceful fallback, all rows returned")

    # Test 8: no filter_json param → returns all rows
    r = api("GET", f"/api/v1/tables/{TABLE_ID}/rows", token)
    assert r.status_code == 200, f"no filter_json: {r.status_code} {r.text[:200]}"
    result_ids = {row["row_id"] for row in r.json()}
    assert result_ids.issuperset(set(row_ids)), f"no filter_json: expected all rows {set(row_ids)}, got {result_ids}"
    print("[ok] API: no filter_json → all rows returned")

    print("\n=== PASSED — e2e_test_row_filter_json ===")
