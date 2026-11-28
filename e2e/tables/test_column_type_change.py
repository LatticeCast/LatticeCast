"""A type change is refused while a stored value does not fit; an int cell is never truncated."""

from __future__ import annotations

from time import time_ns

from e2e_base import BASE, api, create_blank_table


def _add(token, table_id, name, col_type):
    r = api("POST", f"/api/v1/tables/{table_id}/columns", token, json={"name": name, "type": col_type})
    assert r.status_code == 201, r.text[:200]
    return next(c["column_id"] for c in r.json()["columns"] if c["name"] == name)


def test_type_change_and_int_input(authed_page, workspace, admin_token):
    page, token = authed_page, admin_token
    _, ws_name = workspace
    table_id = create_blank_table(token, f"retype_{time_ns()}", ws_name)
    label = _add(token, table_id, "label", "text")
    count = _add(token, table_id, "count", "int")
    r = api("POST", f"/api/v1/tables/{table_id}/rows", token, json={"row_data": {label: "abc", count: 7}})
    assert r.status_code == 201, r.text[:200]
    row_path = f"/api/v1/tables/{table_id}/rows/{r.json()['row_id']}"
    row_id = r.json()["row_id"]

    # "abc" is not an int: PostgreSQL refuses the change and the column stays text.
    r = api("PATCH", f"/api/v1/tables/{table_id}/columns/{label}", token, json={"type": "int"})
    assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"
    assert "do not fit" in r.text, r.text[:200]
    columns = api("GET", f"/api/v1/tables/{table_id}", token).json()["columns"]
    assert next(c["type"] for c in columns if c["column_id"] == label) == "text"

    # An index built for the old type is dropped with it, so it cannot refuse a later write.
    code = _add(token, table_id, "code", "int")
    r = api("POST", f"/api/v1/tables/{table_id}/columns/{code}/index", token)
    assert r.status_code == 201, r.text[:200]
    r = api("PATCH", f"/api/v1/tables/{table_id}/columns/{code}", token, json={"type": "text"})
    assert r.status_code == 200, r.text[:200]
    indexes = api("GET", f"/api/v1/tables/{table_id}/indexes", token).json()["columns"]
    assert next(c["index"] for c in indexes if c["column_id"] == code) is None
    r = api("PATCH", row_path, token, json={"row_data": {code: "99999999999999999999"}})
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    # Every int fits a double, so that change is accepted.
    r = api("PATCH", f"/api/v1/tables/{table_id}/columns/{count}", token, json={"type": "double"})
    assert r.status_code == 200, r.text[:200]
    r = api("PATCH", f"/api/v1/tables/{table_id}/columns/{count}", token, json={"type": "int"})
    assert r.status_code == 200, r.text[:200]

    # Typing a fraction into the int cell is refused, not truncated to 1.
    r = api("POST", f"/api/v1/tables/{table_id}/views", token, json={"name": "Grid", "type": "table"})
    assert r.status_code == 201, r.text[:200]
    page.goto(f"{BASE}/{ws_name}/{table_id}", wait_until="domcontentloaded")
    page.get_by_test_id("view-tab-Grid").click()
    page.locator("td", has_text="7").first.click()
    cell = page.locator('input[type="number"]')
    cell.fill("1.9")
    with page.expect_response(lambda resp: resp.request.method == "PATCH" and resp.url.endswith(f"/rows/{row_id}")) as sent:
        cell.press("Enter")
    assert sent.value.status == 422, sent.value.status
    assert api("GET", row_path, token).json()["row_data"][count] == 7
