# LatticeCast — Storage Architecture

MinIO provides S3-compatible object storage through async `aioboto3`. There are
two distinct key spaces: generic user files and table-row Markdown documents.

## Runtime Flow

```text
frontend/controller -> FastAPI -> config/storage.py -> MinIO bucket
```

`backend/src/config/storage.py` creates async S3 clients and ensures the bucket
exists during application startup.

## Generic User Files

Routes in `backend/src/router/api/storage.py` expose list/download/upload/delete
under `/api/v1/storage`.

- Non-admin keys are automatically prefixed with a stable prefix derived from
  the user's UUID; clients see paths without that prefix.
- Admins may address full keys and list the whole bucket.
- Paths strip leading slashes and reject `..` traversal.
- Frontend JSON helpers live in `frontend/src/lib/backend/storage.ts`.

This API is for general per-user files. It is not the ticket-document API.

## Table Documents

Routes in `backend/src/router/api/rows.py` access Markdown objects directly:

```text
{workspace_id}/{table_id}/{row_id}.md
{workspace_id}/{table_id}/col-{column_id}/{row_id}.md
```

- The first segment is the UUID `workspace_id`, never `workspace_name` or
  `user_name`.
- The second segment is `table_id`; `workspace_name` and `table_id` cannot
  contain `.` because they are also browser/storage path-facing values.
- Creating a row best-effort creates objects for document columns and stores
  their keys in `row_data`.
- Main-document reads may inject live hierarchy links into template comments.
- Deleting a row also performs document cleanup.
- `/docs-exist` batches object discovery for the table UI.

## Main Files

| Concern | Source |
|---|---|
| Client/bucket setup | `backend/src/config/storage.py` |
| Generic storage API | `backend/src/router/api/storage.py` |
| Row document API | `backend/src/router/api/rows.py` |
| Generic FE client | `frontend/src/lib/backend/storage.ts` |
| Ticket-doc FE client | `frontend/src/lib/backend/tables.ts` |
| Settings | `.env.example`, `backend/src/config/settings.py` |

## Gotchas

- Use only awaitable S3 calls in FastAPI paths.
- Preserve the distinction between user-prefixed generic keys and
  workspace/table document keys.
- Resolve and authorize the table through PostgreSQL before touching its
  document objects.
- Do not expose MinIO credentials or internal endpoints to the browser.
