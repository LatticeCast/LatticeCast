"""E2E test: normalized column names are unique within a table.

The column mutation API must reject names that collide after trimming outer
whitespace and normalizing case. The test deliberately stays at the API layer:
the story introduces no UI validation state, and the database/API boundary is
the behavior users rely on.

Run:
    docker compose --profile test up -d e2e
    docker compose exec -T e2e pytest tables/test_column_name_uniqueness.py -v
"""

from __future__ import annotations

import time

from e2e_base import api


def _column(schema: dict, name: str) -> dict:
    column = next((item for item in schema["columns"] if item["name"] == name), None)
    assert column is not None, f"column {name!r} missing from {schema['columns']!r}"
    return column


def test_column_name_uniqueness(admin_token, workspace):
    """Reject duplicate creates and renames without mutating the schema."""
    token = admin_token
    workspace_id, _workspace_name = workspace
    table_id = f"column-unique-{int(time.time() * 1000) % 10_000_000}"

    response = api(
        "POST",
        "/api/v1/tables",
        token,
        json={"table_id": table_id, "workspace_id": workspace_id},
    )
    assert response.status_code == 201, response.text[:200]

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        token,
        json={"name": "Status", "type": "text"},
    )
    assert response.status_code == 201, response.text[:200]
    status_column = _column(response.json(), "Status")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        token,
        json={"name": "Priority", "type": "text"},
    )
    assert response.status_code == 201, response.text[:200]
    priority_column = _column(response.json(), "Priority")

    response = api(
        "POST",
        f"/api/v1/tables/{table_id}/columns",
        token,
        json={"name": " status ", "type": "text"},
    )
    assert response.status_code == 409, response.text[:200]
    assert response.json()["detail"] == "A column with that name already exists"

    response = api(
        "PATCH",
        f"/api/v1/tables/{table_id}/columns/{priority_column['column_id']}",
        token,
        json={"name": " STATUS "},
    )
    assert response.status_code == 409, response.text[:200]
    assert response.json()["detail"] == "A column with that name already exists"

    response = api("GET", f"/api/v1/tables/{table_id}", token)
    assert response.status_code == 200, response.text[:200]
    columns = response.json()["columns"]
    assert _column({"columns": columns}, "Status")["column_id"] == status_column["column_id"]
    assert _column({"columns": columns}, "Priority")["column_id"] == priority_column["column_id"]
