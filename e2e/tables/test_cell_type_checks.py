"""PostgreSQL checks every written cell against its column's storage type."""

from __future__ import annotations

from time import time_ns

from e2e_base import api, create_blank_table

# storage type -> (values it takes, values it refuses)
CASES = {
    "text": (["a", "", None], [1, True, ["a"], {"a": 1}]),
    "int": ([3, -3, None], [1.5, "3", True, [3]]),
    "double": ([1.5, 2, None], ["1.5", "abc", True, [1.5]]),
    "strings": ([["a"], [], None], ["a", [1], 1]),
}


def test_every_storage_type_is_checked_on_write(admin_token, workspace):
    token = admin_token
    _, ws_name = workspace
    table_id = create_blank_table(token, f"cells_{time_ns()}", ws_name)
    ids = {}
    for col_type in CASES:
        r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": col_type, "type": col_type})
        assert r.status_code == 201, r.text[:200]
        ids[col_type] = next(c["column_id"] for c in r.json()["columns"] if c["name"] == col_type)

    r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": {}})
    assert r.status_code == 201, r.text[:200]
    row_path = f"/api/v1/tables/{table_id}/rows/{r.json()['row_id']}"

    for col_type, (taken, refused) in CASES.items():
        column = ids[col_type]
        for value in taken:
            r = api("PATCH", row_path, token, json={"row_data": {column: value}})
            assert r.status_code == 200, f"{col_type} {value!r}: {r.status_code} {r.text[:200]}"
        for value in refused:
            r = api("PATCH", row_path, token, json={"row_data": {column: value}})
            assert r.status_code == 422, f"{col_type} {value!r}: {r.status_code} {r.text[:200]}"
            r = api("PUT", row_path, token, json={"row_data": {column: value}})
            assert r.status_code == 422, f"PUT {col_type} {value!r}: {r.status_code} {r.text[:200]}"

    # A new row is checked too.
    r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": {ids["double"]: "x"}})
    assert r.status_code == 422, f"insert: {r.status_code} {r.text[:200]}"
