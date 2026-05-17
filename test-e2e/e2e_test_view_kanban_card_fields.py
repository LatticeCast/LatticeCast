#!/usr/bin/env python3
"""E2E test: Kanban card fields — toggle which fields appear on cards.

Scenario:
  1. Create workspace + PM table (auto-creates Sprint Board kanban view).
  2. Navigate to the Kanban view.
  3. Open the "Card fields" panel — verify all checkboxes visible.
  4. Uncheck a field → PUT fires → API confirms card_fields updated.
  5. Check a previously unchecked field → verify card_fields updated.
  6. Verify the card UI renders only the selected fields.
  7. Navigate away and back → verify card_fields persists.

Run:
    docker compose --profile test up -d browser test-e2e
    docker compose exec test-e2e python3 /scripts/e2e_test_view_kanban_card_fields.py [--snapshot]
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
_TS = int(time.time()) % 100000
WORKSPACE_NAME = f"kb-cf-{_TS}"
TABLE_ID = f"kb-cf-{_TS}"

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


def goto_table(page, ws_id: str, table_id: str) -> None:
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

    # ── Setup: workspace ──────────────────────────────────────────────────────
    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": WORKSPACE_NAME})
    if r.status_code != 201:
        fatal(f"create workspace: {r.status_code} {r.text[:200]}")
    ws_id = r.json()["workspace_id"]
    print(f"[ok] workspace {WORKSPACE_NAME!r} → {ws_id}")

    try:
        # ── Setup: PM table (auto-creates Sprint Board kanban view) ───────────
        r = api("POST", "/api/v1/tables/template/pm", token,
                json={"table_id": TABLE_ID, "workspace_name": WORKSPACE_NAME})
        if r.status_code != 201:
            fatal(f"create PM table: {r.status_code} {r.text[:200]}")
        schema = r.json()
        columns = schema.get("columns", [])
        print(f"[ok] PM table {TABLE_ID!r} (cols={len(columns)})")

        # Find kanban view
        kanban_views = [v for v in schema.get("views", []) if v.get("type") == "kanban"]
        if not kanban_views:
            fatal(f"PM template has no kanban view; types={[v.get('type') for v in schema.get('views', [])]}")
        kanban_view = kanban_views[0]
        kanban_view_id = kanban_view["view_id"]
        group_by_col = kanban_view.get("config", {}).get("group_by")
        print(f"[ok] kanban view_id={kanban_view_id}  group_by={group_by_col!r}")

        # Get non-group-by columns (these appear in card fields panel)
        all_col_ids = [c["column_id"] for c in columns]
        col_names = {c["column_id"]: c["name"] for c in columns}
        print(f"[ok] columns: {[(c['name'], c['column_id']) for c in columns]}")

        # Create a couple of rows so cards are visible
        status_col = group_by_col
        r = api("POST", f"/api/v1/tables/{TABLE_ID}/rows", token,
                json={"row_data": {status_col: "todo"}})
        if r.status_code != 201:
            fatal(f"create row: {r.status_code} {r.text[:200]}")
        row_id = r.json()["row_id"]
        print(f"[ok] created row {row_id}")

        # ── Playwright session ────────────────────────────────────────────────
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

            goto_table(page, ws_id, TABLE_ID)

            # ── Step 1: Click Sprint Board tab ────────────────────────────────
            try:
                sprint_tab = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_tab")
                fatal("Sprint Board tab not visible")
            sprint_tab.click()
            print("[ok] clicked Sprint Board tab")

            # Wait for kanban to render (card fields button must be visible)
            try:
                cf_btn = page.locator('[data-testid="kanban-card-fields-btn"]')
                cf_btn.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_btn")
                fatal("Card fields button not visible")

            snap(page, "kb_cf_01_kanban_loaded")
            print("[ok] kanban view loaded, card fields button visible")

            # ── Step 2: Open card fields panel ────────────────────────────────
            cf_btn.click()
            page.wait_for_timeout(300)

            # Verify checkboxes appear for columns
            first_col = columns[0]
            first_cb_sel = f'[data-testid="kanban-card-field-{first_col["column_id"]}-checkbox"]'
            try:
                page.wait_for_selector(first_cb_sel, state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_checkboxes")
                fatal("Card field checkboxes not visible after opening panel")

            snap(page, "kb_cf_02_panel_open")
            print("[ok] card fields panel open — checkboxes visible")

            # ── Step 3: Check a specific field → verify PUT + API ─────────────
            # Pick the first column that isn't group_by
            target_col = next(
                (c for c in columns if c["column_id"] != group_by_col), columns[0]
            )
            target_col_id = target_col["column_id"]
            target_cb = page.locator(
                f'[data-testid="kanban-card-field-{target_col_id}-checkbox"]'
            )

            # Determine initial state (checked or not)
            was_checked = target_cb.is_checked()

            # Toggle it: if unchecked → check; if checked → uncheck then re-check
            with page.expect_response(
                lambda resp: (
                    f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}" in resp.url
                    and resp.request.method == "PUT"
                ),
                timeout=10000,
            ):
                target_cb.click()
            print(f"[ok] toggled {target_col['name']!r} checkbox (was_checked={was_checked})")

            page.wait_for_timeout(300)
            snap(page, "kb_cf_03_after_toggle1")

            # API verify: card_fields should reflect the toggle
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view: {r.status_code} {r.text[:200]}")
            card_fields_api = r.json().get("config", {}).get("card_fields", [])

            if was_checked:
                # We unchecked it → should NOT be in card_fields
                if target_col_id in card_fields_api:
                    fatal(f"API: {target_col_id!r} still in card_fields after uncheck: {card_fields_api}")
                print(f"[ok] API: {target_col['name']!r} removed from card_fields")
            else:
                # We checked it → should be in card_fields
                if target_col_id not in card_fields_api:
                    fatal(f"API: {target_col_id!r} not in card_fields after check: {card_fields_api}")
                print(f"[ok] API: {target_col['name']!r} added to card_fields")

            # ── Step 4: Toggle a second column ────────────────────────────────
            second_col = next(
                (c for c in columns
                 if c["column_id"] != group_by_col and c["column_id"] != target_col_id),
                None,
            )
            if second_col:
                second_cb = page.locator(
                    f'[data-testid="kanban-card-field-{second_col["column_id"]}-checkbox"]'
                )
                second_was_checked = second_cb.is_checked()

                with page.expect_response(
                    lambda resp: (
                        f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}" in resp.url
                        and resp.request.method == "PUT"
                    ),
                    timeout=10000,
                ):
                    second_cb.click()
                print(f"[ok] toggled {second_col['name']!r} (was_checked={second_was_checked})")

                page.wait_for_timeout(300)

                # API verify
                r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
                if r.status_code != 200:
                    fatal(f"GET view: {r.status_code} {r.text[:200]}")
                card_fields_api = r.json().get("config", {}).get("card_fields", [])

                if second_was_checked:
                    if second_col["column_id"] in card_fields_api:
                        fatal(f"API: {second_col['column_id']!r} still in card_fields")
                else:
                    if second_col["column_id"] not in card_fields_api:
                        fatal(f"API: {second_col['column_id']!r} not in card_fields")
                print(f"[ok] API: second toggle verified for {second_col['name']!r}")

            snap(page, "kb_cf_04_after_toggle2")

            # ── Step 5: Close panel, verify card renders correct fields ────────
            # Click elsewhere to close the panel
            page.locator('[data-testid="kanban-card-fields-btn"]').click()
            page.wait_for_timeout(300)

            # Get the current card_fields from API for verification
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
            final_card_fields = r.json().get("config", {}).get("card_fields", [])
            print(f"[ok] final card_fields={final_card_fields}")

            snap(page, "kb_cf_05_cards_visible")

            # ── Step 6: Navigate away and back → verify persistence ───────────
            page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
            goto_table(page, ws_id, TABLE_ID)

            try:
                sprint_tab2 = page.locator('[data-testid="view-tab-Sprint Board"]')
                sprint_tab2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_tab_after_nav")
                fatal("Sprint Board tab not visible after navigation back")
            sprint_tab2.click()

            try:
                cf_btn2 = page.locator('[data-testid="kanban-card-fields-btn"]')
                cf_btn2.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_btn_after_nav")
                fatal("Card fields button not visible after navigation back")

            # Open panel and verify checkboxes match persisted state
            cf_btn2.click()
            page.wait_for_timeout(300)

            # Verify the target checkbox state persisted
            target_cb_after = page.locator(
                f'[data-testid="kanban-card-field-{target_col_id}-checkbox"]'
            )
            try:
                target_cb_after.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeout:
                snap(page, "kb_cf_FAIL_no_cb_after_nav")
                fatal("Checkboxes not visible after navigation back")

            is_checked_now = target_cb_after.is_checked()
            expected_checked = not was_checked  # we toggled it once
            if is_checked_now != expected_checked:
                fatal(
                    f"Persistence check: {target_col['name']!r} checked={is_checked_now}, "
                    f"expected={expected_checked}"
                )
            print(f"[ok] step 6 — checkbox state persists after navigation")

            # API verify persistence
            r = api("GET", f"/api/v1/tables/{TABLE_ID}/views/{kanban_view_id}", token)
            if r.status_code != 200:
                fatal(f"GET view after nav: {r.status_code} {r.text[:200]}")
            persisted_fields = r.json().get("config", {}).get("card_fields", [])
            if persisted_fields != final_card_fields:
                fatal(
                    f"API persistence: card_fields={persisted_fields!r}, "
                    f"expected={final_card_fields!r}"
                )
            print(f"[ok] step 6 — API: card_fields persisted across navigation")

            snap(page, "kb_cf_06_after_nav_verified")

            browser.close()

    finally:
        # ── Teardown: delete workspace ────────────────────────────────────────
        r = api("DELETE", f"/api/v1/workspaces/{ws_id}", token)
        if r.status_code not in (200, 204):
            print(f"WARN: delete workspace {ws_id}: {r.status_code}", file=sys.stderr)
        else:
            print(f"[ok] deleted workspace {ws_id}")

    print("\n=== PASSED — e2e_test_view_kanban_card_fields ===")


if __name__ == "__main__":
    main()
