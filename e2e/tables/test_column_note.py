"""A column's note is entered when the column is added and shown under its name.

Three pillars:
  - Playwright UI    — the add-column modal takes a note; the header shows it
  - BE API verify    — GET /tables/{id} returns options.note
  - Durability check — the note is still shown after a reload
"""

from __future__ import annotations

from time import time_ns

from e2e_base import BASE, api

NOTE = "Epoch ms, shown as a due date"


def _snap(page, name: str, enabled: bool) -> None:
    if enabled:
        page.screenshot(path=f"/output/{name}.png", full_page=True)


def test_column_note_is_entered_and_shown(authed_page, workspace, admin_token, snapshot):
    page = authed_page
    _, ws_name = workspace
    r = api(
        "POST", "/api/v1/tables", admin_token,
        json={"table_name": f"note-{time_ns()}", "workspace_id": ws_name},
    )
    assert r.status_code == 201, r.text[:200]
    table_id = r.json()["table_id"]
    assert r.json()["columns"] == []

    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)

    # An empty table offers the add-column button; the modal takes a note.
    page.get_by_test_id("grid-add-column-btn").click()
    page.get_by_test_id("add-column-name-input").fill("Due")
    page.get_by_test_id("add-column-note-input").fill(NOTE)
    with page.expect_response(
        lambda resp: resp.request.method == "POST" and resp.url.endswith(f"/tables/{table_id}/columns"),
        timeout=10000,
    ) as created:
        page.get_by_test_id("add-column-submit-btn").click()
    assert created.value.status == 201

    # BE pillar: the note is stored on the column.
    r = api("GET", f"/api/v1/tables/{table_id}", admin_token)
    assert r.status_code == 200, r.text[:200]
    column = next(c for c in r.json()["columns"] if c["name"] == "Due")
    assert column["options"]["note"] == NOTE

    # UI pillar: the header shows it under the name.
    note = page.get_by_test_id(f"col-note-{column['column_id']}")
    note.wait_for(state="visible", timeout=8000)
    assert note.inner_text().strip() == NOTE
    _snap(page, "column_note_01_header", snapshot)

    # Durability: still shown after a reload.
    page.reload(wait_until="domcontentloaded", timeout=20000)
    page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    note = page.get_by_test_id(f"col-note-{column['column_id']}")
    note.wait_for(state="visible", timeout=8000)
    assert note.inner_text().strip() == NOTE
