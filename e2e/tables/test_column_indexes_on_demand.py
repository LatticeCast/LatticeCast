"""Per-column indexes are on demand: btree for text and int, GIN for strings, none for double or blob."""

from __future__ import annotations

from time import time_ns

from e2e_base import api, create_blank_table


def _add(token, table_id, name, col_type, **options):
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": name, "type": col_type, "options": options})
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
        due = _add(token, table_id, "due", "int", note="when it is due", display="date")
        qty = _add(token, table_id, "qty", "double")
        status = _add(token, table_id, "status", "text", display="select")
        done = _add(token, table_id, "done", "strings", display="checkbox")
        doc = _add(token, table_id, "doc", "blob", kind="text")

        # The note and display hint round-trip through the schema; the server only stores them.
        assert due["options"]["note"] == "when it is due"
        assert due["options"]["display"] == "date"
        assert status["options"].get("note") is None

        # Adding a column creates no index. text and strings equality still has the shared GIN.
        for column in (due, qty, status, done, doc):
            assert _state(token, table_id, column["column_id"])["index"] is None, column["name"]
        assert _state(token, table_id, due["column_id"])["served_by"] == "none"
        assert _state(token, table_id, status["column_id"])["served_by"] == "shared_gin"
        assert _state(token, table_id, done["column_id"])["served_by"] == "shared_gin"

        # text and int take a btree, strings (an array of strings) a GIN, and the listing shows it.
        for column, method in ((due, "btree"), (status, "btree"), (done, "gin")):
            state = _state(token, table_id, column["column_id"])
            assert state["can_create_index"] is True, column["name"]
            r = api("POST", f"/api/v1/tables/{table_id}/columns/{column['column_id']}/index", token)
            assert r.status_code == 201, f"{column['name']}: {r.status_code} {r.text[:200]}"
            assert r.json()["index"]["method"] == method, f"{column['name']}: {r.json()['index']}"
            assert _state(token, table_id, column["column_id"])["served_by"] == method

        # double and blob are never indexed.
        for column in (qty, doc):
            assert _state(token, table_id, column["column_id"])["can_create_index"] is False, column["name"]
            r = api("POST", f"/api/v1/tables/{table_id}/columns/{column['column_id']}/index", token)
            assert r.status_code == 422, f"{column['name']}: {r.status_code} {r.text[:200]}"
            # The refusal is PostgreSQL's own, relayed: the API keeps no second copy of the rule.
            assert "only text, int and strings columns take a per-column index" in r.text, r.text[:200]

        # Dropping returns each column to unindexed.
        for column in (due, status, done):
            r = api("DELETE", f"/api/v1/tables/{table_id}/columns/{column['column_id']}/index", token)
            assert r.status_code == 200, r.text[:200]
            assert _state(token, table_id, column["column_id"])["index"] is None

        r = api("POST", f"/api/v1/tables/{table_id}/columns/not-a-column/index", token)
        assert r.status_code == 404, r.text[:200]

        # The types that only described a reading can no longer be created.
        for retired in ("select", "checkbox", "url", "date", "datetime", "number", "string", "tags"):
            r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": f"old_{retired}", "type": retired})
            assert r.status_code == 422, f"{retired}: {r.status_code} {r.text[:200]}"
    finally:
        api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)
