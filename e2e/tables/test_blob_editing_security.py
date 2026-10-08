"""A row with a document remains editable and renders sanitized Markdown."""

from uuid import uuid4

from playwright.sync_api import expect

from e2e_base import BASE, api


def test_document_row_edits_and_sanitized_preview(authed_page, admin_token, workspace, snapshot):
    page = authed_page
    ws_id, _ = workspace
    table_id = f"blob-edit-{uuid4().hex[:12]}"
    result = api("POST", "/api/v1/tables", admin_token, json={"table_id": table_id, "workspace_id": ws_id})
    assert result.status_code == 201, result.text
    columns = {}
    for name, kind, options in (("Label", "text", {}), ("Done", "checkbox", {}), ("Notes", "blob", {"kind": "text"})):
        result = api("POST", f"/api/v1/tables/{table_id}/columns", admin_token,
                     json={"name": name, "type": kind, "options": options})
        assert result.status_code == 201, result.text
        columns[name] = next(c["column_id"] for c in result.json()["columns"] if c["name"] == name)
    result = api("POST", f"/api/v1/tables/{table_id}/views", admin_token,
                 json={"name": "Table", "type": "table", "config": {}})
    assert result.status_code == 201, result.text
    result = api("POST", f"/api/v1/tables/{table_id}/rows", admin_token,
                 json={"row_data": {columns["Label"]: "before", columns["Done"]: False}})
    assert result.status_code == 201, result.text
    row_id = result.json()["row_id"]
    row_path = f"/api/v1/tables/{table_id}/rows/{row_id}"
    payload = b'# Safe heading\n\n<img src="invalid:" onerror="window.blobXss=1">\n\n[bad](javascript:window.blobXss=2)'
    result = api("PUT", f"{row_path}/blob/{columns['Notes']}", admin_token,
                 files={"file": ("notes.md", payload, "text/markdown")})
    assert result.status_code == 200, result.text
    metadata = result.json()

    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    page.get_by_test_id("view-tab-Table").click()
    checkbox = page.get_by_test_id(f"checkbox-cell-{row_id}-{columns['Done']}")
    checkbox.wait_for(state="visible")
    with page.expect_response(lambda response: response.url.endswith(row_path) and response.request.method == "PATCH") as changed:
        checkbox.click()
    assert changed.value.status == 200
    result = api("GET", row_path, admin_token)
    assert result.json()["row_data"][columns["Done"]] is True
    assert result.json()["row_data"][columns["Notes"]] == metadata

    page.get_by_test_id(f"doc-open-{row_id}-{columns['Notes']}").click()
    editor = page.get_by_test_id("doc-cell-editor")
    expect(editor).to_be_visible()
    preview = page.get_by_test_id("doc-cell-editor-preview")
    expect(preview.locator("h1")).to_have_text("Safe heading")
    assert preview.locator("[onerror], script, a[href^='javascript:']").count() == 0
    assert page.evaluate("window.blobXss === undefined")
    assert api("GET", f"{row_path}/blob/{columns['Notes']}", admin_token).content == payload
    if snapshot:
        page.screenshot(path="/output/blob_safe_markdown.png", full_page=True)
    page.get_by_test_id("doc-cell-editor-close").click()
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.goto(f"{BASE}/{ws_id}/{table_id}", wait_until="domcontentloaded")
    page.get_by_test_id("view-tab-Table").click()
    expect(page.get_by_test_id(f"checkbox-cell-{row_id}-{columns['Done']}")).to_have_attribute("aria-checked", "true")
    result = api("GET", row_path, admin_token)
    assert result.json()["row_data"][columns["Notes"]] == metadata
