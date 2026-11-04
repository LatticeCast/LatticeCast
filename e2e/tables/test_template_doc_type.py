"""Template seeds expose text blob columns without legacy doc vocabulary."""

from __future__ import annotations

import time

import pytest

from e2e_base import api


@pytest.mark.parametrize("kind", ("blank", "crm", "pm"))
def test_template_doc_columns_are_text_blobs(admin_token, workspace, kind):
    workspace_id, _ = workspace
    name = f"seed-doc-type-{kind}-{time.time_ns()}"
    path = "/api/v1/tables" if kind == "blank" else f"/api/v1/tables/template/{kind}"
    response = api(
        "POST", path, admin_token,
        json={"table_name": name, "workspace_id": workspace_id},
    )
    assert response.status_code == 201, (
        f"{kind} table: {response.status_code} {response.text[:200]}"
    )
    columns = response.json()["columns"]
    doc = next((col for col in columns if col["name"] == "Doc"), None)
    assert doc is not None, f"{kind} template has no Doc column"
    assert doc["type"] == "blob", f"{kind} Doc type: {doc}"
    assert doc["options"]["kind"] == "text", f"{kind} Doc kind: {doc}"
    assert all(col["type"] != "doc" for col in columns)
    assert all(col.get("options", {}).get("kind") != "doc" for col in columns)
