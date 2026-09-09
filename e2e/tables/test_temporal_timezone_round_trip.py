"""E2E: a temporal cell round-trips through the user's configured timezone.

Server times are epoch milliseconds in UTC with no zone (V48-V55). The
frontend is the only place a timezone exists, and the zone it uses comes from
the user's config, not the browser. So:

  write   the picked calendar day is read IN that zone -> the instant that
          day begins there  (offset applied in reverse)
  read    that instant is rendered back IN that zone -> the same day
          (offset applied forward)

The defining property, and the one this file exists to pin: the SAME stored
instant renders as a DIFFERENT day for a reader in a different zone. Nothing
else covered that. test_row_update and test_column_datetime_type check what
gets stored; neither checks that the zone is actually applied, so all three
of config-zone / reverse-on-write / forward-on-read could break without a
failing test.

Usage:
    docker compose exec -T e2e pytest tables/test_temporal_timezone_round_trip.py -v [--snapshot]
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api, seed_login_info

# +8 with no DST, and -5/-4 with DST. A day boundary sits between them, which
# is the whole point: one instant, two calendar days.
ZONE_AHEAD = "Asia/Taipei"
ZONE_BEHIND = "America/New_York"
MS_PER_DAY = 86_400_000

PICKED_DAY = "2026-07-15"
DATE_COL = "Starts On"
DATETIME_COL = "Starts At"


def snap(page, name: str, snapshot: bool) -> None:
    if snapshot:
        page.screenshot(path=f"/output/{name}.png")


def _set_zone(token: str, zone: str) -> None:
    r = api("PATCH", "/api/v1/login/me/config", token, json={"timezone": zone})
    assert r.status_code == 200, f"set timezone {zone}: {r.status_code} {r.text[:200]}"
    assert r.json().get("timezone") == zone, f"config did not keep the zone: {r.json()}"


def _cell(page, row_id: int, col_index: int):
    """A grid cell. There is no per-cell testid; the row has one and the
    column is a position, as in the rest of tables/."""
    row = page.locator(f'[data-testid="grid-row-{row_id}"]')
    return row.locator(f"td:nth-child({col_index + 2})")


def _cell_text(page, row_id: int, col_index: int) -> str:
    return _cell(page, row_id, col_index).inner_text().strip()


def _utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def test_temporal_timezone_round_trip(browser, workspace, admin_token, snapshot):
    token = admin_token
    ws_id, ws_name = workspace
    table_id = f"tz-{int(time.time() * 1000) % 10_000_000}"

    # ── Setup: table + one date column and one datetime column ───────────
    r = api("POST", "/api/v1/tables", token, json={"table_id": table_id, "workspace_id": ws_name})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"

    col_ids: dict[str, str] = {}
    for name, col_type in ((DATE_COL, "date"), (DATETIME_COL, "datetime")):
        r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": name, "type": col_type})
        assert r.status_code in (200, 201), f"create {name}: {r.status_code} {r.text[:200]}"
        col = next((c for c in r.json()["columns"] if c["name"] == name), None)
        assert col is not None, f"{name} missing from schema: {r.json()['columns']}"
        col_ids[name] = col["column_id"]
    r = api("GET", f"/api/v1/tables/{table_id}", token)
    assert r.status_code == 200, f"get table: {r.status_code} {r.text[:200]}"
    col_order = [c["column_id"] for c in r.json().get("columns", [])]
    idx_date = col_order.index(col_ids[DATE_COL])
    idx_datetime = col_order.index(col_ids[DATETIME_COL])
    print(f"[setup] table {table_id!r} date@{idx_date} datetime@{idx_datetime}")

    r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": {}})
    assert r.status_code == 201, f"create row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]

    # ── Pick a day while configured as +8 ────────────────────────────────
    _set_zone(token, ZONE_AHEAD)
    print(f"[ok] config timezone = {ZONE_AHEAD}")

    page = browser.new_page(viewport={"width": 1400, "height": 800})
    try:
        seed_login_info(page, token, "lattice", role="admin")
        page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="networkidle", timeout=25000)

        cell = _cell(page, row_id, idx_date)
        cell.wait_for(state="visible", timeout=15000)
        cell.click()

        date_input = cell.locator("input[type='date']")
        try:
            date_input.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            pytest.fail("date input did not appear after clicking the cell")
        date_input.fill(PICKED_DAY)
        with page.expect_response(
            lambda resp: f"/rows/{row_id}" in resp.url and resp.request.method in ("PUT", "PATCH"),
            timeout=10000,
        ):
            date_input.press("Enter")

        # ── The stored value is the instant that day BEGINS in +8 ────────
        r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
        assert r.status_code == 200, f"get row: {r.status_code} {r.text[:200]}"
        stored = r.json()["row_data"].get(col_ids[DATE_COL])
        assert isinstance(stored, int), f"date cell should store an integer instant, got {stored!r}"

        expected = int(
            datetime.fromisoformat(f"{PICKED_DAY}T00:00:00").replace(
                tzinfo=timezone(timedelta(hours=8))
            ).timestamp()
            * 1000
        )
        assert stored == expected, (
            f"expected the instant {PICKED_DAY}T00:00+08:00 ({expected}), got {stored} "
            f"which is {_utc_day(stored)} in UTC — the offset was not applied in reverse on write"
        )
        # It is NOT UTC midnight: V55 removed that flooring precisely so the
        # offset could survive. A floored value would read back a day early.
        assert stored % MS_PER_DAY != 0, (
            f"{stored} is UTC-midnight aligned, so the +8 offset was discarded"
        )
        print(f"[ok] write: picked {PICKED_DAY} in +8 -> {stored} (= {_utc_day(stored)} in UTC)")

        # ── Read back in +8: the same day the user picked ────────────────
        page.reload(wait_until="networkidle", timeout=25000)
        _cell(page, row_id, idx_date).wait_for(state="visible", timeout=15000)
        shown_ahead = _cell_text(page, row_id, idx_date)
        assert shown_ahead == PICKED_DAY, (
            f"in {ZONE_AHEAD} the cell should show {PICKED_DAY}, showed {shown_ahead!r}"
        )
        assert str(stored) not in shown_ahead, f"the raw epoch value leaked into the UI: {shown_ahead!r}"
        print(f"[ok] read in {ZONE_AHEAD}: {shown_ahead}")
        snap(page, "tz_01_ahead", snapshot)

        # ── Same instant, reader moved to -4/-5: the PREVIOUS day ────────
        _set_zone(token, ZONE_BEHIND)
        page.reload(wait_until="networkidle", timeout=25000)
        _cell(page, row_id, idx_date).wait_for(state="visible", timeout=15000)
        shown_behind = _cell_text(page, row_id, idx_date)

        r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", token)
        assert r.json()["row_data"].get(col_ids[DATE_COL]) == stored, (
            "changing the display zone must not rewrite the stored instant"
        )
        assert shown_behind != shown_ahead, (
            f"both zones rendered {shown_ahead!r} — the configured zone is being ignored, "
            "which is what this test exists to catch"
        )
        assert shown_behind == "2026-07-14", (
            f"{PICKED_DAY}T00:00+08:00 is 2026-07-14 in {ZONE_BEHIND}, cell showed {shown_behind!r}"
        )
        print(f"[ok] read in {ZONE_BEHIND}: {shown_behind} — same instant, previous day")
        snap(page, "tz_02_behind", snapshot)

        # ── datetime uses the same path, and shows the time as well ──────
        _set_zone(token, ZONE_AHEAD)
        instant = expected + 13 * 3600 * 1000 + 45 * 60 * 1000  # 13:45 local
        r = api(
            "PATCH",
            f"/api/v1/tables/{table_id}/rows/{row_id}",
            token,
            json={"row_data": {col_ids[DATETIME_COL]: instant}},
        )
        assert r.status_code == 200, f"patch datetime: {r.status_code} {r.text[:200]}"
        page.reload(wait_until="networkidle", timeout=25000)
        _cell(page, row_id, idx_datetime).wait_for(state="visible", timeout=15000)
        shown_dt = _cell_text(page, row_id, idx_datetime)
        assert shown_dt == f"{PICKED_DAY} 13:45", (
            f"datetime cell in {ZONE_AHEAD} should show '{PICKED_DAY} 13:45', showed {shown_dt!r}"
        )
        print(f"[ok] datetime in {ZONE_AHEAD}: {shown_dt}")
        snap(page, "tz_03_datetime", snapshot)

        print("\n=== PASSED — test_temporal_timezone_round_trip ===")
    finally:
        _set_zone(token, ZONE_AHEAD)
        page.close()
        api("DELETE", f"/api/v1/tables/{table_id}", token)
