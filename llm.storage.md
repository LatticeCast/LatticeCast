# Storage and Blob Cells

`config/storage.py` supplies async S3-compatible clients. Storage credentials need bucket-level listing and object read/write/delete permissions for the configured bucket.

Two key spaces:

- `/storage`: generic files; non-admin paths are user-UUID prefixed.
- Table blob cells: metadata in `row_data[column_id]`, object key `{workspace_id}/{table_id}/rows/{row_id}/blobs/{column_id}`.

Every blob kind uses `GET|PUT|DELETE /tables/{table}/rows/{row}/blob/{column}`. A `text` kind conventionally stores plain text or Markdown, but it has no separate route.

- Authorize and resolve table/row/column before touching storage.
- Blob metadata is updated through `update_blob_cell`, never ordinary row patch/put.
- Do not expose storage credentials/endpoints to the browser.
