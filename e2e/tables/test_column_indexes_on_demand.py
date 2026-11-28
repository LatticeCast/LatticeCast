"""Per-column indexes are on demand, and a column can carry a note."""

from __future__ import annotations

from time import time_ns

from e2e_base import api, create_blank_table


def _add(token, table_id, name, kind, **options):
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": name, "type": kind, "options": options})
    assert r.status_code == 201, r.text[:200]
    return next(c for c in r.json()["columns"] if c["name"] == name)


def _state(token, table_id, column_id):
    r = api("GET", f"/api/v1/tables/{table_id}/indexes", token)
    assert r.status_code == 200, r.text[:200]
    return next(c for c in r.json()["columns"] if c["column_id"] == column_id)


def test_indexes_are_created_only_on_request(admin_token):
    token = admin_token
    created = api("POST", "/api/v1/workspaces", token, json={"workspace_name": f"idx-od-{time_ns()}"})
    assert created.status_code == 201, created.text[:200]
    workspace_id = created.json()["workspace_id"]
    try:
        table_id = create_blank_table(token, "idx_probe", workspace_id)
        due = _add(token, table_id, "due", "date", note="when it is due", display="date")
        qty = _add(token, table_id, "qty", "number")
        tag = _add(token, table_id, "label", "select")
        note = _add(token, table_id, "memo", "text")

        # The note and display hint round-trip through the schema.
        assert due["options"]["note"] == "when it is due"
        assert due["options"]["display"] == "date"
        assert note["options"].get("note") is None

        # Adding a column creates no index.
        assert _state(token, table_id, due["column_id"])["index"] is None
        assert _state(token, table_id, due["column_id"])["served_by"] == "none"
        assert _state(token, table_id, due["column_id"])["can_create_index"] is True
        assert _state(token, table_id, qty["column_id"])["index"] is None
        assert _state(token, table_id, tag["column_id"])["served_by"] == "shared_gin"

        # An integer-valued type can ask for a btree, and the listing shows it.
        r = api("POST", f"/api/v1/tables/{table_id}/columns/{due['column_id']}/index", token)
        assert r.status_code == 201, r.text[:200]
        assert r.json()["index"]["method"] == "btree"
        assert _state(token, table_id, due["column_id"])["served_by"] == "btree"

        # number may hold fractions; select / text are served by the shared GIN: both refuse.
        for column in (qty, tag, note):
            r = api("POST", f"/api/v1/tables/{table_id}/columns/{column['column_id']}/index", token)
            assert r.status_code == 422, f"{column['name']}: {r.status_code} {r.text[:200]}"

        # Dropping returns the column to unindexed.
        r = api("DELETE", f"/api/v1/tables/{table_id}/columns/{due['column_id']}/index", token)
        assert r.status_code == 200, r.text[:200]
        assert _state(token, table_id, due["column_id"])["index"] is None

        r = api("POST", f"/api/v1/tables/{table_id}/columns/not-a-column/index", token)
        assert r.status_code == 404, r.text[:200]
    finally:
        api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)
