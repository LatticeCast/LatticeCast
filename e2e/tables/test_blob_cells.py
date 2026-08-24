"""Blob-cell API integration contract.

This test deliberately stays API-only: blob cells have no user-facing rendering
in this story. It proves that file metadata is server-managed and that both
explicit doc-blob routes and the legacy row-doc compatibility routes address
the same stored document.
"""

from __future__ import annotations

import time

import requests

from e2e_base import BASE, api


def _column_id(schema: dict, name: str) -> str:
    column = next((item for item in schema["columns"] if item["name"] == name), None)
    assert column is not None, f"column {name!r} missing from schema"
    return column["column_id"]


def test_blob_cells_round_trip(admin_token, workspace):
    """Files replace atomically; docs round-trip through both API contracts."""
    ws_id, _ws_name = workspace
    table_id = f"blob-cells-{int(time.time() * 1000) % 10_000_000}"

    response = api("POST", "/api/v1/tables", admin_token, json={"table_id": table_id, "workspace_id": ws_id})
    assert response.status_code == 201, f"create table: {response.status_code} {response.text[:200]}"
    default_doc_column_id = _column_id(response.json(), "Doc")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "Attachment", "type": "blob", "options": {"kind": "file", "accept": "text/plain"}},
    )
    assert response.status_code == 201, f"create file blob column: {response.status_code} {response.text[:200]}"
    file_column_id = _column_id(response.json(), "Attachment")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "Notes", "type": "blob", "options": {"kind": "doc", "accept": "text/markdown,.md"}},
    )
    assert response.status_code == 201, f"create doc blob column: {response.status_code} {response.text[:200]}"
    doc_column_id = _column_id(response.json(), "Notes")

    response = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token, json={"row_data": {}})
    assert response.status_code == 201, f"create row: {response.status_code} {response.text[:200]}"
    row_id = response.json()["row_id"]
    assert response.json()["row_data"].get(default_doc_column_id) is None
    assert response.json()["row_data"].get(doc_column_id) is None

    first_file = b"first blob payload\n"
    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{file_column_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("first.txt", first_file, "text/plain")},
        timeout=15,
    )
    assert response.status_code == 200, f"upload file blob: {response.status_code} {response.text[:200]}"
    first_metadata = response.json()
    assert first_metadata["filename"] == "first.txt"
    assert first_metadata["content_type"] == "text/plain"
    assert first_metadata["size"] == len(first_file)
    assert first_metadata["key"].endswith(f"/rows/{row_id}/blobs/{file_column_id}")

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{file_column_id}", admin_token)
    assert response.status_code == 200, f"download first file: {response.status_code} {response.text[:200]}"
    assert response.content == first_file
    assert response.headers["content-type"].startswith("text/plain")

    replacement_file = b"PK\x03\x04binary zip payload\x00\xff"
    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{file_column_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("archive.zip", replacement_file, "application/zip")},
        timeout=15,
    )
    assert response.status_code == 200, f"replace file blob: {response.status_code} {response.text[:200]}"
    assert response.json()["filename"] == "archive.zip"
    assert response.json()["content_type"] == "application/zip"
    assert response.json()["size"] == len(replacement_file)

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{file_column_id}", admin_token)
    assert response.status_code == 200, f"download replacement file: {response.status_code} {response.text[:200]}"
    assert response.content == replacement_file

    document = "# Blob document\n\nStored in an addressed cell.\n"
    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{doc_column_id}/doc",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "text/plain"},
        data=document.encode(),
        timeout=15,
    )
    assert response.status_code == 200, f"write doc blob: {response.status_code} {response.text[:200]}"
    assert response.json()["filename"] == "Notes.md"

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{doc_column_id}/doc", admin_token)
    assert response.status_code == 200, f"read addressed doc blob: {response.status_code} {response.text[:200]}"
    assert response.text == document

    compatibility_document = "# Compatibility document\n\nStored in the table default doc cell.\n"
    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/doc",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "text/plain"},
        data=compatibility_document.encode(),
        timeout=15,
    )
    assert response.status_code == 200, f"write compatibility doc: {response.status_code} {response.text[:200]}"
    assert response.text == compatibility_document

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}/doc", admin_token)
    assert response.status_code == 200, f"read compatibility doc: {response.status_code} {response.text[:200]}"
    assert response.text == compatibility_document

    response = api(
        "GET", f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{default_doc_column_id}/doc", admin_token
    )
    assert response.status_code == 200, f"read addressed compatibility doc: {response.status_code} {response.text[:200]}"
    assert response.text == compatibility_document

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
    assert response.status_code == 200, f"read row metadata: {response.status_code} {response.text[:200]}"
    row_data = response.json()["row_data"]
    assert row_data[file_column_id]["filename"] == "archive.zip"
    assert row_data[doc_column_id] == {
        "key": f"{ws_id}/{table_id}/rows/{row_id}/blobs/{doc_column_id}",
        "filename": "Notes.md",
        "content_type": "text/markdown",
        "size": len(document.encode()),
    }
