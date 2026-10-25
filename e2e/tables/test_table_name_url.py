"""Browser table paths use names; backend requests keep numeric identities."""

from urllib.parse import urlparse

from e2e_base import BASE, api


def test_table_name_url(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    workspace_id, workspace_name = workspace
    table_name = "data-reports"
    response = api(
        "POST",
        "/api/v1/tables",
        admin_token,
        json={"workspace_id": workspace_id, "table_name": table_name},
    )
    assert response.status_code == 201, response.text[:200]
    table_id = response.json()["table_id"]
    named_path = f"/{workspace_name}/{table_name}"

    # A fresh browser navigation starts with empty sidebar stores.
    page.goto(f"{BASE}{named_path}", wait_until="domcontentloaded")
    page.locator('[data-table-loaded="true"]').wait_for()
    assert urlparse(page.url).path == named_path
    assert page.get_by_test_id("breadcrumb-table").inner_text() == table_name
    if snapshot:
        page.screenshot(path="/output/table_name_url.png", full_page=True)

    page.reload(wait_until="domcontentloaded")
    page.locator('[data-table-loaded="true"]').wait_for()
    assert urlparse(page.url).path == named_path

    page.get_by_test_id("menu-toggle").click()
    page.get_by_test_id(f"sidebar-table-{table_id}").click()
    page.locator('[data-table-loaded="true"]').wait_for()
    assert urlparse(page.url).path == named_path

    # Old numeric bookmarks remain readable and become the named URL.
    page.goto(f"{BASE}/{workspace_name}/{table_id}", wait_until="domcontentloaded")
    page.wait_for_url(f"{BASE}{named_path}")
    page.locator('[data-table-loaded="true"]').wait_for()

    row_response = api(
        "POST", f"/api/v1/tables/{table_id}/rows", admin_token,
        json={"row_data": {}},
    )
    assert row_response.status_code == 201, row_response.text[:200]
    row_id = row_response.json()["row_id"]
    page.goto(f"{BASE}{named_path}/{row_id}", wait_until="domcontentloaded")
    page.get_by_role("link", name="← Back").wait_for()
    assert page.get_by_role("link", name="← Back").get_attribute("href") == named_path
