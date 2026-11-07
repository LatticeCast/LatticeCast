"""A workspace reader cannot create, replace, patch, or delete rows."""

from uuid import uuid4

from e2e_base import api, login


def test_read_only_member_cannot_mutate_rows(admin_token, workspace):
    workspace_id, _ = workspace
    table_name = f"row-perms-{uuid4().hex[:12]}"
    result = api(
        "POST",
        "/api/v1/tables",
        admin_token,
        json={"table_name": table_name, "workspace_id": workspace_id},
    )
    assert result.status_code == 201, result.text
    table_id = result.json()["table_id"]

    result = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        admin_token,
        json={"name": "City", "type": "text"},
    )
    assert result.status_code == 201, result.text
    column_id = next(
        c["column_id"] for c in result.json()["columns"] if c["name"] == "City"
    )

    rows_path = f"/api/v1/tables/{table_id}/rows"
    original = {column_id: "Tokyo"}
    result = api("POST", rows_path, admin_token, json={"row_data": original})
    assert result.status_code == 201, result.text
    row_path = f"{rows_path}/{result.json()['row_id']}"

    email = f"row-reader-{uuid4().hex[:12]}@e2e.local"
    result = api(
        "POST",
        "/api/v1/admin/users",
        admin_token,
        json={"email": email, "role": "user"},
    )
    assert result.status_code == 201, result.text
    user_id = result.json()["user_id"]
    try:
        result = api(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/members",
            admin_token,
            json={"user_email": email, "level": "read"},
        )
        assert result.status_code == 201, result.text
        reader = login(email)
        assert api("GET", row_path, reader).status_code == 200

        for method, path, payload in (
            ("POST", rows_path, {"row_data": {column_id: "Osaka"}}),
            ("PATCH", row_path, {"row_data": {column_id: "Osaka"}}),
            ("PUT", row_path, {"row_data": {column_id: "Osaka"}}),
            ("DELETE", row_path, None),
        ):
            result = api(method, path, reader, json=payload)
            assert result.status_code == 403, (
                f"{method} {path}: {result.status_code} {result.text[:200]}"
            )

        result = api("GET", row_path, admin_token)
        assert result.status_code == 200 and result.json()["row_data"] == original
    finally:
        result = api(
            "DELETE",
            f"/api/v1/workspaces/{workspace_id}/members/{user_id}",
            admin_token,
        )
        assert result.status_code == 204, result.text
        result = api("DELETE", f"/api/v1/admin/users/{email}", admin_token)
        assert result.status_code == 204, result.text
