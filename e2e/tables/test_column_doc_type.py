"""E2E test: e2e_test_column_doc_type — doc column upload + download.

Topic: Writing markdown content into a doc-type column cell via the
DocCellEditor modal persists to MinIO and is readable on re-open.

Three pillars (developing-e2e):
  - Playwright UI    — click "Open doc" button in grid → editor modal opens,
                       type markdown → close (save) → re-open and verify
  - BE API verify    — GET /tables/{tid}/rows/{rid}/doc confirms content saved
  - Cross-view check — navigate away and back, re-open editor, content persists

Flow:
  setup:  login as "lattice" → create workspace → create blank table →
          add doc column → add Table view → add row
  step 1: Table view → click "Open doc" button for the row's doc cell
          → editor modal visible
  step 2: type markdown content into the editor textarea → close modal
          (blur triggers auto-save) → wait for PUT response
  step 3: API verify — GET /tables/{tid}/rows/{rid}/doc returns the content
  step 4: Re-open editor modal → verify textarea shows saved content
  step 5: Navigate away and back → re-open editor → content persists
  teardown: DELETE workspace (conftest fixture)

Run:
    docker compose --profile test up -d browser e2e
    docker compose exec e2e pytest tables/test_column_doc_type.py -v
    docker compose exec e2e pytest tables/test_column_doc_type.py -v --snapshot
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api

_SUFFIX = int(time.time()) % 100000
DOC_CONTENT = "# Test Doc\n\nThis is **bold** and _italic_.\n\n- item 1\n- item 2\n"


def snap(page, name: str, snapshot: bool) -> None:
    if not snapshot:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def goto_table(page, ws_id: str, table_id: str, snapshot: bool) -> None:
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="view-tab-Schema"]', state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_view_tabs", snapshot)
        pytest.fail(f"View tabs did not load for table {table_id}")


def test_column_doc_type(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    ws_id, _ws_name = workspace
    table_id = f"doc-col-{_SUFFIX}"

    print(f"[ok] login 'lattice'")

    # ── 1. workspace provided by fixture ──────────────────────────────────
    print(f"[ok] workspace → {ws_id}")

    # ── 2. Create blank table ─────────────────────────────────────────────
    r = api("POST", "/api/v1/tables", admin_token,
            json={"table_id": table_id, "workspace_id": ws_id})
    assert r.status_code == 201, f"create table: {r.status_code} {r.text[:200]}"
    print(f"[ok] blank table {table_id!r}")

    # ── 3. Add a doc column ───────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/columns", admin_token,
            json={"name": "Notes", "type": "doc", "options": {}})
    assert r.status_code == 201, f"add doc column: {r.status_code} {r.text[:200]}"
    schema = r.json()
    doc_col = next(
        (c for c in schema["columns"] if c.get("name") == "Notes" and c.get("type") == "doc"),
        None,
    )
    assert doc_col, "doc column 'Notes' not found in schema after creation"
    doc_col_id = doc_col["column_id"]
    print(f"[ok] doc column 'Notes' ({doc_col_id[:8]}…)")

    # ── 4. Add a Table view ───────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/views", admin_token,
            json={"name": "Table", "type": "table", "config": {}})
    assert r.status_code == 201, f"add Table view: {r.status_code} {r.text[:200]}"
    print("[ok] added 'Table' view")

    # ── 5. Add a row ─────────────────────────────────────────────────────
    r = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
            json={"row_data": {}})
    assert r.status_code == 201, f"add row: {r.status_code} {r.text[:200]}"
    row_id = r.json()["row_id"]
    print(f"[ok] row added (row_id={row_id})")

    # ── 6. Browser — navigate to table ────────────────────────────────────
    goto_table(page, ws_id, table_id, snapshot)

    # Click Table view tab
    table_tab = '[data-testid="view-tab-Table"]'
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_table_tab", snapshot)
        pytest.fail("'Table' view tab not visible")
    page.click(table_tab)

    # Wait for table grid
    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_table_grid", snapshot)
        pytest.fail("Table grid did not render")

    snap(page, "doc_col_01_initial_table", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Click "Open doc" button in the doc cell
    # ═══════════════════════════════════════════════════════════════════
    doc_btn = f'[data-testid="doc-open-{row_id}-{doc_col_id}"]'
    try:
        page.wait_for_selector(doc_btn, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_doc_btn", snapshot)
        pytest.fail(f"doc-open button not visible for row {row_id}, col {doc_col_id[:8]}…")
    page.click(doc_btn)
    print("[ok] clicked 'Open doc' button")

    # Wait for editor modal to appear
    editor_modal = '[data-testid="doc-cell-editor"]'
    try:
        page.wait_for_selector(editor_modal, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_editor_modal", snapshot)
        pytest.fail("DocCellEditor modal did not appear")
    print("[ok] editor modal visible")

    snap(page, "doc_col_02_editor_open_empty", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Type markdown content and close (triggers save on blur)
    # ═══════════════════════════════════════════════════════════════════
    # The editor may show empty state with "Start writing →" button
    # or directly show the textarea (if doc already exists but empty)
    textarea_sel = '[data-testid="doc-cell-editor-textarea"]'
    start_writing_btn = page.locator(f"{editor_modal} button:has-text('Start writing')")
    if start_writing_btn.count() > 0:
        start_writing_btn.click()
        print("[ok] clicked 'Start writing' button")

    try:
        page.wait_for_selector(textarea_sel, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_textarea", snapshot)
        pytest.fail("doc-cell-editor-textarea not visible")

    page.fill(textarea_sel, DOC_CONTENT)
    print("[ok] typed markdown content into editor")

    snap(page, "doc_col_03_content_typed", snapshot)

    # Close the modal — triggers blur → auto-save → PUT /doc
    close_btn = '[data-testid="doc-cell-editor-close"]'
    with page.expect_response(
        lambda resp: (
            f"/api/v1/tables/{table_id}/rows/{row_id}/doc" in resp.url
            and resp.request.method == "PUT"
            and resp.ok
        ),
        timeout=10000,
    ):
        page.click(close_btn)
    print("[ok] closed editor; PUT /doc confirmed")

    # Verify modal is gone
    page.locator(editor_modal).wait_for(state="hidden", timeout=5000)

    snap(page, "doc_col_04_after_close", snapshot)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: API verify — GET /doc returns the saved content
    # ═══════════════════════════════════════════════════════════════════
    r = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/doc", admin_token)
    assert r.status_code == 200, f"GET doc: {r.status_code} {r.text[:200]}"
    saved_content = r.text
    assert saved_content.strip() == DOC_CONTENT.strip(), (
        f"API: doc content mismatch.\n"
        f"  Expected: {DOC_CONTENT.strip()!r}\n"
        f"  Got:      {saved_content.strip()!r}"
    )
    print("[ok] API: doc content matches what was typed")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Re-open editor → verify content displayed
    # ═══════════════════════════════════════════════════════════════════
    page.click(doc_btn)
    try:
        page.wait_for_selector(editor_modal, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_editor_reopen", snapshot)
        pytest.fail("DocCellEditor modal did not re-appear")

    try:
        page.wait_for_selector(textarea_sel, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_textarea_reopen", snapshot)
        pytest.fail("textarea not visible on re-open")

    textarea_value = page.locator(textarea_sel).input_value()
    assert textarea_value.strip() == DOC_CONTENT.strip(), (
        f"UI re-open: content mismatch.\n"
        f"  Expected: {DOC_CONTENT.strip()!r}\n"
        f"  Got:      {textarea_value.strip()!r}"
    )
    print("[ok] UI: re-opened editor shows saved content")

    snap(page, "doc_col_05_reopen_with_content", snapshot)

    # Close the modal again
    page.click(close_btn)
    page.locator(editor_modal).wait_for(state="hidden", timeout=5000)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Navigate away and back → content persists
    # ═══════════════════════════════════════════════════════════════════
    page.goto(f"{BASE}/{ws_id}/", wait_until="domcontentloaded")
    goto_table(page, ws_id, table_id, snapshot)

    # Switch to Table view
    try:
        page.wait_for_selector(table_tab, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_table_tab_after_nav", snapshot)
        pytest.fail("'Table' view tab not visible after navigation back")
    page.click(table_tab)

    try:
        page.wait_for_selector("table thead", state="visible", timeout=15000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_grid_after_nav", snapshot)
        pytest.fail("Table grid did not render after navigation back")

    # Click doc open button again
    try:
        page.wait_for_selector(doc_btn, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_doc_btn_after_nav", snapshot)
        pytest.fail("doc-open button not visible after navigation back")
    page.click(doc_btn)

    try:
        page.wait_for_selector(editor_modal, state="visible", timeout=8000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_editor_after_nav", snapshot)
        pytest.fail("DocCellEditor modal did not appear after navigation back")

    try:
        page.wait_for_selector(textarea_sel, state="visible", timeout=5000)
    except PlaywrightTimeout:
        snap(page, "doc_col_FAIL_no_textarea_after_nav", snapshot)
        pytest.fail("textarea not visible after navigation back")

    textarea_after_nav = page.locator(textarea_sel).input_value()
    assert textarea_after_nav.strip() == DOC_CONTENT.strip(), (
        f"UI after nav: content not persisted.\n"
        f"  Expected: {DOC_CONTENT.strip()!r}\n"
        f"  Got:      {textarea_after_nav.strip()!r}"
    )
    print("[ok] UI (after nav): doc content persists")

    snap(page, "doc_col_06_after_nav_content_persists", snapshot)

    print("\n=== PASSED — e2e_test_column_doc_type ===")
