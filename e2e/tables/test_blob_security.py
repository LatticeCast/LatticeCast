"""Blob ownership and read-only denial, verified through real API calls."""

from uuid import uuid4

from e2e_base import api, login


def test_blob_write_denial_and_forged_creation(admin_token, workspace):
    ws_id, _ = workspace
    table_id = f"blob-sec-{uuid4().hex[:12]}"
    result = api("POST", "/api/v1/tables", admin_token, json={"table_id": table_id, "workspace_id": ws_id})
    assert result.status_code == 201, result.text
    result = api("POST", f"/api/v1/tables/{table_id}/columns", admin_token,
                 json={"name": "Attachment", "type": "blob", "options": {"kind": "file"}})
    assert result.status_code == 201, result.text
    column_id = next(c["column_id"] for c in result.json()["columns"] if c["name"] == "Attachment")
    result = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token, json={"row_data": {}})
    assert result.status_code == 201, result.text
    row_id = result.json()["row_id"]
    cell = f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{column_id}"
    result = api("PUT", cell, admin_token, files={"file": ("original.txt", b"original bytes", "text/plain")})
    assert result.status_code == 200, result.text
    original = result.json()
    result = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
                 json={"row_data": {column_id: original}})
    assert result.status_code == 422, result.text

    email = f"blob-reader-{uuid4().hex[:12]}@e2e.local"
    result = api("POST", "/api/v1/admin/users", admin_token, json={"email": email, "role": "user"})
    assert result.status_code == 201, result.text
    user_id = result.json()["user_id"]
    try:
        result = api("POST", f"/api/v1/workspaces/{ws_id}/members", admin_token,
                     json={"user_email": email, "level": "read"})
        assert result.status_code == 201, result.text
        reader = login(email)
        assert api("GET", cell, reader).content == b"original bytes"
        result = api("PUT", cell, reader, files={"file": ("attack.txt", b"replaced", "text/plain")})
        assert result.status_code == 403, result.text
        assert api("DELETE", cell, reader).status_code == 403
        assert api("DELETE", f"/api/v1/tables/{table_id}/rows/{row_id}", reader).status_code == 403
        result = api("GET", cell, admin_token)
        assert result.status_code == 200 and result.content == b"original bytes"
        result = api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
        assert result.json()["row_data"][column_id] == original
        result = api("DELETE", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token)
        assert result.status_code == 204, result.text
        assert api("GET", f"/api/v1/tables/{table_id}/rows/{row_id}", admin_token).status_code == 404
        assert api("GET", cell, admin_token).status_code == 404
    finally:
        result = api("DELETE", f"/api/v1/workspaces/{ws_id}/members/{user_id}", admin_token)
        assert result.status_code == 204, result.text
        result = api("DELETE", f"/api/v1/admin/users/{email}", admin_token)
        assert result.status_code == 204, result.text
