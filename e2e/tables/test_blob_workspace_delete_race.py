"""Concurrent blob uploads and workspace deletion must never deadlock."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import time_ns

from e2e_base import api


def _put_blob(gate: Barrier, token: str, table_id: int, row_id: int, doc_column: str):
    gate.wait(timeout=10)
    return api(
        "PUT",
        f"/api/v1/tables/{table_id}/rows/{row_id}/blob/{doc_column}",
        token,
        files={"file": (f"race-{row_id}.md", b"# race\n", "text/markdown")},
        timeout=25,
    )


def _delete_workspace(gate: Barrier, token: str, workspace_id: str):
    gate.wait(timeout=10)
    return api("DELETE", f"/api/v1/workspaces/{workspace_id}", token, timeout=25)


def test_blob_put_during_workspace_delete(admin_token):
    token = admin_token
    for attempt in range(3):
        name = f"blob-delete-race-{time_ns()}-{attempt}"
        created = api(
            "POST", "/api/v1/workspaces", token, json={"workspace_name": name}
        )
        assert created.status_code == 201, created.text[:200]
        workspace_id = created.json()["workspace_id"]
        deleted = False
        try:
            table_response = api(
                "POST",
                "/api/v1/tables",
                token,
                json={"workspace_id": workspace_id, "table_name": "articles"},
            )
            assert table_response.status_code == 201, table_response.text[:200]
            table = table_response.json()
            table_id = table["table_id"]
            doc_column = next(
                c["column_id"] for c in table["columns"] if c["name"] == "Doc"
            )
            row_ids = []
            for _ in range(3):
                row_response = api(
                    "POST",
                    f"/api/v1/tables/{table_id}/rows",
                    token,
                    json={"row_data": {}},
                )
                assert row_response.status_code == 201, row_response.text[:200]
                row_ids.append(row_response.json()["row_id"])

            gate = Barrier(5)

            with ThreadPoolExecutor(max_workers=4) as executor:
                uploads = [
                    executor.submit(
                        _put_blob, gate, token, table_id, row_id, doc_column
                    )
                    for row_id in row_ids
                ]
                deletion = executor.submit(_delete_workspace, gate, token, workspace_id)
                gate.wait(timeout=10)
                upload_results = [future.result(timeout=30) for future in uploads]
                delete_result = deletion.result(timeout=30)

            deleted = delete_result.status_code == 204
            assert deleted, (
                f"workspace DELETE: {delete_result.status_code} {delete_result.text[:200]}"
            )
            for result in upload_results:
                # DELETE may win before an upload acquires its parent lock.
                assert result.status_code in (200, 403, 404), (
                    f"blob PUT: {result.status_code} {result.text[:200]}"
                )
        finally:
            if not deleted:
                api("DELETE", f"/api/v1/workspaces/{workspace_id}", token)
