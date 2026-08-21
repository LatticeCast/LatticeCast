"""E2E coverage for the ordinary-row and blob-cell mutation boundary."""

from __future__ import annotations

from uuid import uuid4

import requests

from e2e_base import BASE, api


def _column_id(schema: dict, name: str) -> str:
    column = next((column for column in schema["columns"] if column["name"] == name), None)
    assert column is not None, f"column {name!r} missing from schema"
    return column["column_id"]


def test_row_and_blob_mutations_use_separate_endpoints(admin_token, workspace):
    """Generic row updates cannot write blob metadata; blob routes cannot write text cells."""
    workspace_id, _workspace_name = workspace
    table_id = f"blob-boundary-{uuid4().hex[:12]}"

    response = api(
        "POST",
        "/api/v1/tables",
        admin_token,
        json={"table_id": table_id, "workspace_id": workspace_id},
    )
    assert response.status_code == 201, f"create table: {response.status_code} {response.text[:200]}"

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "Label", "type": "text"},
    )
    assert response.status_code == 201, f"create text column: {response.status_code} {response.text[:200]}"
    text_column_id = _column_id(response.json(), "Label")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "Attachment", "type": "blob", "options": {"kind": "file"}},
    )
    assert response.status_code == 201, f"create blob column: {response.status_code} {response.text[:200]}"
    blob_column_id = _column_id(response.json(), "Attachment")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/rows",
        admin_token,
        json={"row_data": {text_column_id: "before"}},
    )
    assert response.status_code == 201, f"create row: {response.status_code} {response.text[:200]}"
    row_id = response.json()["row_id"]

    response = api(
        "PUT",
        f"/api/v1/tables/{table_id}/rows/{row_id}",
        admin_token,
        json={"row_data": {text_column_id: "ordinary update"}},
    )
    assert response.status_code == 200, f"update text cell: {response.status_code} {response.text[:200]}"
    assert response.json()["row_data"][text_column_id] == "ordinary update"

    response = api(
        "PUT",
        f"/api/v1/tables/{table_id}/rows/{row_id}",
        admin_token,
        json={"row_data": {blob_column_id: {"filename": "forbidden.txt"}}},
    )
    assert response.status_code >= 400, f"generic blob mutation unexpectedly succeeded: {response.text[:200]}"

    payload = b"authoritative blob payload\n"
    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{blob_column_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("attachment.txt", payload, "text/plain")},
        timeout=15,
    )
    assert response.status_code == 200, f"upload blob: {response.status_code} {response.text[:200]}"
    metadata = response.json()
    assert metadata == {
        "key": f"{workspace_id}/{table_id}/rows/{row_id}/blobs/{blob_column_id}",
        "filename": "attachment.txt",
        "content_type": "text/plain",
        "size": len(payload),
    }

    response = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
    assert response.status_code == 200, f"read blob metadata: {response.status_code} {response.text[:200]}"
    assert response.json()["row_data"][blob_column_id] == metadata

    response = requests.put(
        f"{BASE}/api/v1/tables/{table_id}/rows/{row_id}/blob/{text_column_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("not-allowed.txt", b"not a blob", "text/plain")},
        timeout=15,
    )
    assert response.status_code == 422, f"non-blob endpoint accepted upload: {response.status_code} {response.text[:200]}"
    assert response.json()["detail"] == "Column is not a blob column"
