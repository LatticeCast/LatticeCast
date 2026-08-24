# Storage and Blob Cells

`config/storage.py` supplies async S3-compatible clients. Storage credentials need bucket-level listing and object read/write/delete permissions for the configured bucket.

Two key spaces:

- `/storage`: generic files; non-admin paths are user-UUID prefixed.
- Table blob cells: metadata in `row_data[column_id]`, object key `{workspace_id}/{table_id}/rows/{row_id}/blobs/{column_id}`.

Doc blob routes are `GET|PUT /tables/{table}/rows/{row}/blob/{column}/doc`; generic blob routes use the same address without `/doc`.

- Authorize and resolve table/row/column before touching storage.
- Blob metadata is updated through `update_blob_cell`, never ordinary row patch/put.
- Do not expose storage credentials/endpoints to the browser.
