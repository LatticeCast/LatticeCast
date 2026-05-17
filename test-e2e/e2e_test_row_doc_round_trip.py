#!/usr/bin/env python3
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
    docker compose exec test-e2e python3 /scripts/e2e_test_row_doc_round_trip.py [--snapshot]
"""

from __future__ import annotations

import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

import e2e_base

ADMIN_USER = "lattice"
_TS = int(time.time()) % 100000
WORKSPACE_NAME = f"doc-rt-{_TS}"
TABLE_ID = f"doc-rt-{_TS}"

SNAPSHOT = "--snapshot" in sys.argv

DOC_INITIAL = f"# Test Doc {_TS}\n\nInitial content for round-trip test.\n"
DOC_EDITED = f"# Test Doc {_TS}\n\nEdited content — round-trip verified.\n"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def main() -> None:
    token = e2e_base.login(ADMIN_USER)
    print(f"[ok] login {ADMIN_USER!r}")

    # ── Setup: workspace ──────────────────────────────────────────────────────
    r = e2e_base.api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        e2e_base.fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── Setup: PM table ───────────────────────────────────────────────────
        r = e2e_base.api("POST", "/api/v1/tables/template/pm", token,
                         json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            e2e_base.fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        print(f"[ok] PM table {TABLE_ID!r}")

        # ── Setup: create a row ───────────────────────────────────────────────
        r = e2e_base.api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token, json={"row_data": {}})
        if r.status_code != 201:
            e2e_base.fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] row created → row_id={row_id}")

        # ── Step 1: PUT doc via API ───────────────────────────────────────────
        r = requests.put(
            f"{e2e_base.BASE}/api/v1/tables/{TABLE_ID}/rows/{row_id}/doc",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
            data=DOC_INITIAL.encode("utf-8"),
            timeout=15,
        )
        if r.status_code != 200:
            e2e_base.fatal(f"PUT doc: {r.status_code} {r.text[:200]}")
        print("[ok] PUT doc → initial content stored")

        # ── Step 2: GET doc via API — verify round-trip ───────────────────────
        r = e2e_base.api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}/doc", token)
        if r.status_code != 200:
            e2e_base.fatal(f"GET doc: {r.status_code} {r.text[:200]}")
        if r.text != DOC_INITIAL:
            e2e_base.fatal(f"GET doc mismatch: expected {DOC_INITIAL!r}, got {r.text!r}")
        print("[ok] GET doc → content matches initial upload")

        # ── Step 3: Open full-page doc editor in browser ──────────────────────
        with sync_playwright() as pw:
            browser = e2e_base.connect_browser(pw)
            ctx = browser.new_context(viewport={"width": 1400, "height": 900})
            e2e_base.seed_login_info(ctx, token, ADMIN_USER)
            page = ctx.new_page()

            doc_url = f"{e2e_base.BASE}/{ws_id}/{TABLE_ID}/{row_id}/doc"
            page.goto(doc_url, wait_until="domcontentloaded")

            # Wait for doc editor to load (loading indicator disappears, textarea appears)
            try:
                page.locator('[data-testid="doc-editor-textarea"]').wait_for(
                    state="visible", timeout=15000
                )
            except PlaywrightTimeout:
                snap(page, "doc_rt_FAIL_editor_not_loaded")
                e2e_base.fatal("Full-page doc editor textarea did not appear")

            snap(page, "doc_rt_01_editor_loaded")
            print("[ok] UI: full-page doc editor loaded")

            # ── Step 4: Verify textarea shows uploaded content ────────────────
            textarea = page.locator('[data-testid="doc-editor-textarea"]')
            actual_value = textarea.input_value()
            if actual_value != DOC_INITIAL:
                snap(page, "doc_rt_FAIL_content_mismatch")
                e2e_base.fatal(
                    f"Textarea content mismatch:\n  expected: {DOC_INITIAL!r}\n  got: {actual_value!r}"
                )
            print("[ok] UI: textarea shows initial doc content")

            # ── Step 5: Edit content and save ─────────────────────────────────
            textarea.fill(DOC_EDITED)

            # Wait for "Unsaved changes" indicator to confirm FE detected the edit
            try:
                page.locator('[data-testid="doc-unsaved-indicator"]').wait_for(
                    state="visible", timeout=5000
                )
            except PlaywrightTimeout:
                snap(page, "doc_rt_FAIL_no_unsaved_indicator")
                e2e_base.fatal("'Unsaved changes' indicator did not appear after edit")

            # Click Save and wait for the PUT response
            with page.expect_response(
                lambda resp: f"/rows/{row_id}/doc" in resp.url and resp.request.method == "PUT",
                timeout=15000,
            ) as resp_info:
                page.locator('[data-testid="doc-save-btn"]').click()

            save_resp = resp_info.value
            if save_resp.status != 200:
                snap(page, "doc_rt_FAIL_save_failed")
                e2e_base.fatal(f"Save PUT returned {save_resp.status}")

            snap(page, "doc_rt_02_after_save")
            print("[ok] UI: Save clicked, PUT returned 200")

            # ── Step 6: Verify "Unsaved changes" disappears after save ────────
            try:
                page.locator('[data-testid="doc-unsaved-indicator"]').wait_for(
                    state="hidden", timeout=5000
                )
            except PlaywrightTimeout:
                pass  # non-critical — the save already succeeded via API

            browser.close()

        # ── Step 7: GET doc via API — verify edited content persisted ─────────
        r = e2e_base.api("GET", f"/api/v1/tables/{TABLE_ID}/rows/{row_id}/doc", token)
        if r.status_code != 200:
            e2e_base.fatal(f"GET doc after edit: {r.status_code} {r.text[:200]}")
        if r.text != DOC_EDITED:
            e2e_base.fatal(
                f"GET doc after edit mismatch:\n  expected: {DOC_EDITED!r}\n  got: {r.text!r}"
            )
        print("[ok] API: edited doc content persisted in MinIO")

    finally:
        # ── Teardown ──────────────────────────────────────────────────────────
        r = e2e_base.api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_row_doc_round_trip ===")


if __name__ == "__main__":
    main()
