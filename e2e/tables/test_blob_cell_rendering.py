"""E2E coverage for rendering and downloading a file blob cell.

The API owns uploaded blob metadata. This test proves the table UI reads that
metadata after navigation and gives the user a working download action.
"""

from __future__ import annotations

import time

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from e2e_base import BASE, api


def _column_id(schema: dict, name: str) -> str:
    column = next((item for item in schema["columns"] if item["name"] == name), None)
    assert column is not None, f"column {name!r} missing from schema"
    return column["column_id"]


def test_blob_cell_renders_and_downloads(authed_page, workspace, admin_token, snapshot):
    """An uploaded file appears in the table and downloads its exact bytes."""
    page = authed_page
    ws_id, _ws_name = workspace
    table_id = f"blob-render-{int(time.time() * 1000) % 10_000_000}"
    filename = "release-notes.txt"
    payload = b"Blob cell content verified through the browser.\n"

    response = api(
        "POST",
        "/api/v1/tables",
        admin_token,
        json={"table_id": table_id, "workspace_id": ws_id},
    )
    assert response.status_code == 201, f"create table: {response.status_code} {response.text[:200]}"

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "Attachment", "type": "blob", "options": {"kind": "file"}},
    )
    assert response.status_code == 201, f"create blob column: {response.status_code} {response.text[:200]}"
    column_id = _column_id(response.json(), "Attachment")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/views",
        admin_token,
        json={"name": "Table", "type": "table", "config": {}},
    )
    assert response.status_code == 201, f"create table view: {response.status_code} {response.text[:200]}"

    response = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token, json={"row_data": {}})
    assert response.status_code == 201, f"create row: {response.status_code} {response.text[:200]}"
    row_id = response.json()["row_id"]

    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{column_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": (filename, payload, "text/plain")},
        timeout=15,
    )
    assert response.status_code == 200, f"upload blob: {response.status_code} {response.text[:200]}"

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
    assert response.status_code == 200, f"read row: {response.status_code} {response.text[:200]}"
    assert response.json()["row_data"][column_id] == {
        "key": f"{ws_id}/{table_id}/rows/{row_id}/blobs/{column_id}",
        "filename": filename,
        "content_type": "text/plain",
        "size": len(payload),
    }

    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    table_tab = page.get_by_test_id("view-tab-Table")
    try:
        table_tab.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout as error:
        raise AssertionError("Table view tab did not render") from error
    table_tab.click()

    # The grid's affordance was renamed blob-download -> blob-open in ef57edb
    # (2026-08-21); one button now covers both doc-open and file-download and
    # the title says which. This test was written against the older name.
    blob_button = page.get_by_test_id(f"blob-open-{row_id}-{column_id}")
    try:
        blob_button.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout as error:
        raise AssertionError("Uploaded blob was not rendered in the table") from error
    assert blob_button.get_attribute("title") == f"Download {filename}"
    assert blob_button.locator("span").all_inner_texts() == [filename, f"{len(payload)} B"]

    if snapshot:
        page.screenshot(path="/output/blob_cell_rendering.png", full_page=True)

    with page.expect_download(timeout=15_000) as download_info:
        blob_button.click()
    download = download_info.value
    assert download.suggested_filename == filename
    assert download.failure() is None

    response = api(
        "GET", f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{column_id}", admin_token
    )
    assert response.status_code == 200, f"read downloaded blob: {response.status_code} {response.text[:200]}"
    assert response.content == payload
