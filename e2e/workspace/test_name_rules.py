"""PostgreSQL refuses a reserved workspace name and a blank view name; the API relays it."""

from __future__ import annotations

from time import time_ns

from e2e_base import BASE, api, create_blank_table


def test_reserved_workspace_name_and_blank_view_name_are_refused(admin_token):
    token = admin_token

    r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": "Settings"})
    assert r.status_code == 422, f"create reserved: {r.status_code} {r.text[:200]}"
    assert "workspaces_workspace_name_not_reserved" in r.text, r.text[:200]

    created = api("POST", "/api/v1/workspaces", token, json={"workspace_name": f"names-{time_ns()}"})
    assert created.status_code == 201, created.text[:200]
    workspace_id = created.json()["workspace_id"]
    try:
        r = api("PUT", f"/api/v1/workspaces/{workspace_id}", token, json={"workspace_name": "api"})
        assert r.status_code == 422, f"rename to reserved: {r.status_code} {r.text[:200]}"

        table_id = create_blank_table(token, "view_names", workspace_id)
        r = api("POST", f"/api/v1/tables/{table_id}/views", token, json={"name": "  ", "type": "table"})
        assert r.status_code == 422, f"blank view name: {r.status_code} {r.text[:200]}"
        assert "table_views_name_not_blank" in r.text, r.text[:200]

        r = api("POST", f"/api/v1/tables/{table_id}/views", token, json={"name": "Grid", "type": "table"})
        assert r.status_code == 201, r.text[:200]
        view_id = next(v["view_id"] for v in r.json()["views"] if v.get("name") == "Grid")
        r = api("PUT", f"/api/v1/tables/{table_id}/views/{view_id}", token, json={"name": ""})
        assert r.status_code == 422, f"blank rename: {r.status_code} {r.text[:200]}"
    finally:
        api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)


def test_workspace_names_need_not_be_unique(admin_token):
    token = admin_token
    name = f"twin-{time_ns()}"
    ids = []
    try:
        for chosen in (name, name, f"other-{time_ns()}"):
            r = api("POST", "/api/v1/workspaces", token, json={"workspace_name": chosen})
            assert r.status_code == 201, f"create {chosen}: {r.status_code} {r.text[:200]}"
            ids.append(r.json()["workspace_id"])

        # Renaming onto an existing name is allowed too.
        r = api("PUT", f"/api/v1/workspaces/{ids[2]}", token, json={"workspace_name": name})
        assert r.status_code == 200, f"rename to a taken name: {r.status_code} {r.text[:200]}"

        # The id still addresses one workspace; the shared name is refused, never guessed.
        for workspace_id in ids:
            r = api("GET", f"/api/v1/workspaces/{workspace_id}", token)
            assert r.status_code == 200 and r.json()["workspace_id"] == workspace_id, r.text[:200]
        r = api("GET", f"/api/v1/workspaces/{name}", token)
        assert r.status_code == 409, f"lookup by shared name: {r.status_code} {r.text[:200]}"
        r = api("POST", "/api/v1/tables", token, json={"table_name": "lost", "workspace_id": name})
        assert r.status_code == 409, f"create table by shared name: {r.status_code} {r.text[:200]}"
    finally:
        for workspace_id in ids:
            api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)


def test_duplicate_workspace_urls_take_a_suffix(authed_page, admin_token):
    """Same name twice: the first keeps `/name/`, the second is `/name-1/`."""
    page = authed_page
    name = f"urltwin-{time_ns()}"
    ids = []
    try:
        for index in range(2):
            r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": name})
            assert r.status_code == 201, r.text[:200]
            ids.append(r.json()["workspace_id"])
            create_blank_table(admin_token, f"only_in_{index}", ids[-1])

        for index, slug in enumerate((name, f"{name}-1")):
            page.goto(f"{BASE}/{slug}/", wait_until="domcontentloaded")
            tab = page.get_by_test_id(f"workspace-tab-{ids[index]}")
            tab.wait_for(state="visible", timeout=15000)
            assert tab.get_attribute("href") == f"/{slug}/"
            assert "bg-blue-600" in tab.get_attribute("class"), f"{slug} did not open workspace {index}"
            page.goto(f"{BASE}/{slug}/only_in_{index}", wait_until="domcontentloaded")
            page.wait_for_selector('[data-table-loaded="true"]', timeout=15000)
    finally:
        for workspace_id in ids:
            api("DELETE", f"/api/v1/workspaces/{workspace_id}", admin_token)
