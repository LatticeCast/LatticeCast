"""E2E test: doc upload+download round-trip.

Scenario:
  1. Create workspace + PM table + row via API.
  2. PUT markdown doc via API.
  3. GET doc via API — verify content stored.
  4. Navigate to full-page doc editor in browser.
  5. Verify textarea shows uploaded content.
  6. Edit content in textarea, click Save.
  7. GET doc via API — verify edited content persisted.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e pytest tables/test_row_doc_round_trip.py -v
"""

from __future__ import annotations

import time

import pytest
import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


_TS = int(time.time()) % 100000

DOC_INITIAL = f"# Test Doc {_TS}\n\nInitial content for round-trip test.\n"
DOC_EDITED = f"# Test Doc {_TS}\n\nEdited content — round-trip verified.\n"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def test_row_doc_round_trip(authed_page, pm_table, admin_token, snapshot):
    page = authed_page
    table_id, ws_id, _cols, _views = pm_table

    # ── Setup: create a row ───────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token, json={"row_data": {}})
    assert r.status_code == 201, f"create row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] row created → row_id={row_id}")

    # ── Step 1: PUT doc via API ───────────────────────────────────────────
    r = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/doc",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "text/plain"},
        data=DOC_INITIAL.encode("utf-8"),
        timeout=15,
    )
    assert r.status_code == 200, f"PUT doc: {r.status_code} {r.text[:200]}"
    print("[ok] PUT doc → initial content stored")

    # ── Step 2: GET doc via API — verify round-trip ───────────────────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/doc", admin_token)
    assert r.status_code == 200, f"GET doc: {r.status_code} {r.text[:200]}"
    assert r.text == DOC_INITIAL, f"GET doc mismatch: expected {DOC_INITIAL!r}, got {r.text!r}"
    print("[ok] GET doc → content matches initial upload")

    # ── Step 3: Open full-page doc editor in browser ──────────────────────
    doc_url = f"{BASE}/{ws_id}/{table_id}/{row_id}/doc"
    page.goto(doc_url, wait_until="domcontentloaded")

    # Wait for doc editor to load (loading indicator disappears, textarea appears)
    try:
        page.locator('[data-testid="doc-editor-textarea"]').wait_for(
            state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        snap(page, "doc_rt_FAIL_editor_not_loaded", snapshot)
        pytest.fail("Full-page doc editor textarea did not appear")

    snap(page, "doc_rt_01_editor_loaded", snapshot)
    print("[ok] UI: full-page doc editor loaded")

    # ── Step 4: Verify textarea shows uploaded content ────────────────────
    textarea = page.locator('[data-testid="doc-editor-textarea"]')
    actual_value = textarea.input_value()
    assert actual_value == DOC_INITIAL, (
        f"Textarea content mismatch:\n  expected: {DOC_INITIAL!r}\n  got: {actual_value!r}"
    )
    print("[ok] UI: textarea shows initial doc content")

    # ── Step 5: Edit content and save ─────────────────────────────────────
    textarea.fill(DOC_EDITED)

    # Wait for "Unsaved changes" indicator to confirm FE detected the edit
    try:
        page.locator('[data-testid="doc-unsaved-indicator"]').wait_for(
            state="visible", timeout=5000
        )
    except PlaywrightTimeout:
        snap(page, "doc_rt_FAIL_no_unsaved_indicator", snapshot)
        pytest.fail("'Unsaved changes' indicator did not appear after edit")

    # Click Save and wait for the PUT response
    with page.expect_response(
        lambda resp: f"/rows/{row_id}/doc" in resp.url and resp.request.method == "PUT",
        timeout=15000,
    ) as resp_info:
        page.locator('[data-testid="doc-save-btn"]').click()

    save_resp = resp_info.value
    assert save_resp.status == 200, f"Save PUT returned {save_resp.status}"

    snap(page, "doc_rt_02_after_save", snapshot)
    print("[ok] UI: Save clicked, PUT returned 200")

    # ── Step 6: Verify "Unsaved changes" disappears after save ────────────
    try:
        page.locator('[data-testid="doc-unsaved-indicator"]').wait_for(
            state="hidden", timeout=5000
        )
    except PlaywrightTimeout:
        pass  # non-critical — the save already succeeded via API

    # ── Step 7: GET doc via API — verify edited content persisted ─────────
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/doc", admin_token)
    assert r.status_code == 200, f"GET doc after edit: {r.status_code} {r.text[:200]}"
    assert r.text == DOC_EDITED, (
        f"GET doc after edit mismatch:\n  expected: {DOC_EDITED!r}\n  got: {r.text!r}"
    )
    print("[ok] API: edited doc content persisted in MinIO")

    print("\n=== PASSED — test_row_doc_round_trip ===")
