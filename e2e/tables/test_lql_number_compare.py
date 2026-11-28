"""LQL ordering comparisons on number columns are numeric, never text."""

from __future__ import annotations

from time import time_ns

from e2e_base import api, create_blank_table


def _lql(token: str, workspace_id: str, text: str):
    return api("POST", f"/api/v1/workspaces/{workspace_id}/lql", token, json={"lql": text})


def test_number_columns_compare_numerically(admin_token):
    token = admin_token
    created = api("POST", "/api/v1/workspaces", token, json={"workspace_name": f"lql-num-{time_ns()}"})
    assert created.status_code == 201, created.text[:200]
    workspace_id = created.json()["workspace_id"]
    try:
        table_id = create_blank_table(token, "jobs", workspace_id)
        ids = {}
        for name, kind in (("tries", "int"), ("max_tries", "int"), ("status", "text")):
            r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": name, "type": kind})
            assert r.status_code == 201, r.text[:200]
            ids[name] = next(c["column_id"] for c in r.json()["columns"] if c["name"] == name)

        rows = [  # tries, max_tries, status
            (3, 10, "FAIL"),
            (12, 20, "FAIL"),
            (9, 9, "OK"),
            (None, 5, "FAIL"),  # an empty cell must neither match nor error
        ]
        for tries, max_tries, status in rows:
            data = {ids["max_tries"]: max_tries, ids["status"]: status}
            if tries is not None:
                data[ids["tries"]] = tries
            r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": data})
            assert r.status_code == 201, r.text[:200]

        def count(filter_text: str) -> int:
            r = _lql(token, workspace_id, f'table("jobs") | filter((r) -> {{ {filter_text} }}) | aggregate(count())')
            assert r.status_code == 200, f"{filter_text}: {r.status_code} {r.text[:200]}"
            return r.json()["rows"][0]["measure"]

        assert count("r.tries < 10") == 2  # 3 and 9; as text '12' < '9' and '3' > '10' would be wrong
        assert count('r.tries < "10"') == 2
        assert count("r.tries >= 10") == 1
        assert count("r.tries <= r.max_tries") == 3  # 3<=10, 12<=20, 9<=9
        assert count('r.status == "FAIL" && r.tries < r.max_tries') == 2

        # A value that is not a number is the caller's error: 4xx, never 500.
        r = _lql(token, workspace_id, 'table("jobs") | filter((r) -> { r.tries < "abc" }) | aggregate(count())')
        assert 400 <= r.status_code < 500, f"{r.status_code} {r.text[:200]}"
    finally:
        api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)
