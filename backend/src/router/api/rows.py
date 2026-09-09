# router/api/rows.py

import re
from io import BytesIO
from typing import Annotated
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from config.storage import s3_client
from middleware.auth import get_current_user, get_rls_session
from models.row import Row, RowCreate, RowPut, RowResponse, RowUpdate
from models.user import User
from repository.row import RowRepository
from repository.table_view import TableViewRepository
from util.pg_errors import http_error_for

from .tables._shared import _get_table_for_member

router = APIRouter(tags=["rows"])


class BlobCellMetadata(BaseModel):
    """Descriptor stored in ``row_data[column_id]``; the object body is in S3-compatible storage."""

    key: str = Field(description="Server-owned object key; clients must not construct or edit it.")
    filename: str = Field(description="Original upload filename or generated Markdown filename.")
    content_type: str = Field(description="Stored MIME type, such as application/zip.")
    size: int = Field(description="Object size in bytes.", ge=0)


def _blob_storage_key(workspace_id: str, table_id: str, row_id: int, column_id: str) -> str:
    """Build a blob key only from stable workspace/table/row/column identifiers."""
    return f"{workspace_id}/{table_id}/rows/{row_id}/blobs/{column_id}"


async def _get_blob_column(table, column_id: str, session: AsyncSession) -> dict:
    """Return a blob column or reject a missing/non-blob cell address."""
    columns = (await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id))["columns"]
    column = next((column for column in columns if column["column_id"] == column_id), None)
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    if column.get("type") != "blob":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Column is not a blob column")
    return column


async def _get_doc_column(table, column_id: str, session: AsyncSession) -> dict:
    """Return an explicitly addressed markdown blob column."""
    columns = (await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id))["columns"]
    column = next((column for column in columns if column["column_id"] == column_id), None)
    if not column:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    if column.get("type") != "blob" or column.get("options", {}).get("kind") != "doc":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Column is not a doc blob column")
    return column


async def _get_default_doc_column(table, session: AsyncSession) -> dict | None:
    """Find the legacy row-doc target without assuming a fixed column name."""
    columns = (await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id))["columns"]
    return next(
        (
            column
            for column in columns
            if column.get("type") == "blob" and column.get("options", {}).get("kind") == "doc"
        ),
        None,
    )


async def _read_blob_content(key: str) -> bytes | None:
    try:
        async with s3_client() as s3:
            response = await s3.get_object(Bucket=settings.minio.bucket, Key=key)
            return await response["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return None
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


def _cell_blob_key(cell_value: object) -> str | None:
    """Read a storage key from current metadata or a legacy string cell value."""
    if isinstance(cell_value, dict) and isinstance(cell_value.get("key"), str):
        return cell_value["key"]
    return cell_value if isinstance(cell_value, str) else None


def _build_doc_template(row_type: str, key: str, title: str) -> str:
    """Generate a markdown doc template based on ticket type."""
    heading = f"# {key}: {title}" if key else f"# {title}"
    if row_type == "epic":
        return f"""{heading}

## Overview
<!-- High-level description of this epic -->

## Stories
<!-- Links to child stories -->

## Acceptance Criteria
- [ ] ...

## Notes
"""
    if row_type == "story":
        return f"""{heading}

## Parent
<!-- [PARENT-KEY] parent title -->

## Description
<!-- What needs to be done -->

## Tasks
<!-- Links to child tasks -->

## Technical Notes
"""
    # task / bug (default)
    steps = "\n## Steps to Reproduce\n1. ...\n" if row_type == "bug" else ""
    return f"""{heading}

## Parent
<!-- [PARENT-KEY] parent title -->

## Description
<!-- Implementation details -->
{steps}
## Solution
<!-- How it was solved -->
"""


async def _inject_hierarchy(content: str, table, row: Row, session: AsyncSession) -> str:
    """Replace placeholder comments in doc with live parent/children links."""
    columns = (await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id))["columns"]
    cols = {c["name"]: c["column_id"] for c in columns}
    key_col_id = cols.get("Key", "")
    title_col_id = cols.get("Title", "")
    parent_col_id = cols.get("Parent", "")
    status_col_id = cols.get("Status", "")
    repo = RowRepository(session)

    # Inject parent link — parent column stores row_id (integer)
    if parent_col_id and re.search(r"<!--\s*\[PARENT-KEY\]", content):
        parent_row_num_str = row.row_data.get(parent_col_id)
        parent_link = ""
        if parent_row_num_str:
            try:
                parent_row = await repo.get_by_number(table.workspace_id, table.table_id, int(str(parent_row_num_str)))
                if parent_row:
                    p_key = parent_row.row_data.get(key_col_id, "") if key_col_id else ""
                    p_title = parent_row.row_data.get(title_col_id, "") if title_col_id else str(parent_row_num_str)
                    parent_link = f"[{p_key}] {p_title}" if p_key else p_title
            except (ValueError, Exception):
                pass
        if parent_link:
            content = re.sub(r"<!--\s*\[PARENT-KEY\][^>]*-->", parent_link, content)

    # Inject children links — filter by row_id (integer) stored in parent column
    if parent_col_id and re.search(r"<!--\s*Links to child", content):
        try:
            children = await repo.filter_by_jsonb(table.workspace_id, table.table_id, {parent_col_id: str(row.row_id)})
            if children:
                lines = []
                for child in children:
                    c_key = child.row_data.get(key_col_id, "") if key_col_id else ""
                    c_title = child.row_data.get(title_col_id, "") if title_col_id else ""
                    c_status = child.row_data.get(status_col_id, "") if status_col_id else ""
                    line = f"- [{c_key}] {c_title}"
                    if c_status:
                        line += f" — {c_status}"
                    lines.append(line)
                children_text = "\n".join(lines)
                content = re.sub(r"<!--\s*Links to child[^>]*-->", children_text, content)
        except Exception:
            pass

    return content


# --------------------------------------------------
# ROWS (nested under table for create/list)
# --------------------------------------------------


@router.post("/tables/{table_id}/rows", response_model=RowResponse, status_code=status.HTTP_201_CREATED)
async def create_row(
    table_id: str,
    data: RowCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Create a new row in a table (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    try:
        # A raw INSERT still passes through trg_rows_canonical_ts (V49), so a
        # bad timestamp is rejected here too, not only on patch/put.
        return await repo.create(
            workspace_id=table.workspace_id,
            table_id=table.table_id,
            row_data=data.row_data,
            created_by=user.user_id,
            updated_by=user.user_id,
        )
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


@router.get("/tables/{table_id}/rows", response_model=list[RowResponse])
async def list_rows(
    table_id: str,
    offset: int = 0,
    limit: int = 100,
    sort: str = "desc",
    filter_json: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List rows. sort=desc|asc. filter_json = JSONB containment filter e.g. {"col_id":"value"}"""
    table = await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    if filter_json:
        import json as json_mod

        try:
            contains = json_mod.loads(filter_json)
        except Exception:
            contains = {}
        if contains:
            return await repo.filter_by_jsonb(
                workspace_id=table.workspace_id, table_id=table.table_id, contains=contains, offset=offset, limit=limit
            )
    return await repo.list_by_table(
        workspace_id=table.workspace_id, table_id=table.table_id, offset=offset, limit=limit, sort=sort
    )


# --------------------------------------------------
# ROWS (nested update/delete by row_id)
# --------------------------------------------------


@router.get("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def get_row(
    table_id: str,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Get a single row by row_id (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    return row


@router.patch("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def patch_row(
    table_id: str,
    row_id: int,
    data: RowUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Merge partial non-blob row data by row_id."""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    try:
        return await repo.patch_row(row=row, data=data, updated_by=user.user_id)
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


@router.put("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def put_row(
    table_id: str,
    row_id: int,
    data: RowPut,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Replace all non-blob row data by row_id; blob metadata is preserved."""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    try:
        return await repo.put_row(row=row, data=data, updated_by=user.user_id)
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


@router.get("/tables/{table_id}/rows/{row_id}/doc", response_class=PlainTextResponse)
async def get_row_doc(
    table_id: str,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> str:
    """Compatibility route for the table's first doc blob column."""
    table = await _get_table_for_member(table_id, user, session)
    doc_column = await _get_default_doc_column(table, session)
    if not doc_column:
        return ""
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    key = _cell_blob_key(row.row_data.get(doc_column["column_id"]))
    if not key:
        return ""
    content_bytes = await _read_blob_content(key)
    if content_bytes is None:
        return ""
    content = content_bytes.decode("utf-8")

    if content and (re.search(r"<!--\s*\[PARENT-KEY\]", content) or re.search(r"<!--\s*Links to child", content)):
        content = await _inject_hierarchy(content, table, row, session)

    return content


@router.put("/tables/{table_id}/rows/{row_id}/doc", response_class=PlainTextResponse)
async def put_row_doc(
    table_id: str,
    row_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> str:
    """Compatibility route for saving to the table's first doc blob column."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        if file_field is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Missing 'file' field in multipart form"
            )
        body = (await file_field.read()).decode("utf-8")
    else:
        body = (await request.body()).decode("utf-8")

    table = await _get_table_for_member(table_id, user, session)
    doc_column = await _get_default_doc_column(table, session)
    if not doc_column:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Table has no doc blob column")
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    key = _blob_storage_key(str(table.workspace_id), table.table_id, row.row_id, doc_column["column_id"])
    try:
        async with s3_client() as s3:
            await s3.put_object(
                Bucket=settings.minio.bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="text/markdown",
            )
        await repo.update_blob(
            row,
            doc_column["column_id"],
            BlobCellMetadata(
                key=key,
                filename=(
                    row.row_data.get(doc_column["column_id"], {}).get("filename")
                    if isinstance(row.row_data.get(doc_column["column_id"]), dict)
                    else f"{doc_column['name']}.md"
                )
                or f"{doc_column['name']}.md",
                content_type="text/markdown",
                size=len(body.encode("utf-8")),
            ).model_dump(),
            updated_by=user.user_id,
        )
        return body
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


@router.get("/tables/{table_id}/docs-exist")
async def batch_docs_exist(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, list[int]]:
    """Compatibility route reporting rows whose default doc blob cell is non-empty."""
    table = await _get_table_for_member(table_id, user, session)
    doc_column = await _get_default_doc_column(table, session)
    if not doc_column:
        return {"row_ids": []}
    rows = await RowRepository(session).list_by_table(table.workspace_id, table.table_id, limit=1000)
    return {"row_ids": [row.row_id for row in rows if _cell_blob_key(row.row_data.get(doc_column["column_id"]))]}


@router.get("/tables/{table_id}/rows/{row_id}/col-doc/{column_id}", response_class=PlainTextResponse)
async def get_col_doc(
    table_id: str,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> str:
    """Legacy alias for the canonical doc blob cell endpoint."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_doc_column(table, column_id, session)
    row = await RowRepository(session).get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    key = _cell_blob_key(row.row_data.get(column_id))
    if not key:
        return ""
    content = await _read_blob_content(key)
    return content.decode("utf-8") if content is not None else ""


@router.put("/tables/{table_id}/rows/{row_id}/col-doc/{column_id}", response_class=PlainTextResponse)
async def put_col_doc(
    table_id: str,
    row_id: int,
    column_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> str:
    """Legacy alias for the canonical doc blob cell endpoint."""
    body = (await request.body()).decode("utf-8")

    table = await _get_table_for_member(table_id, user, session)
    column = await _get_doc_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    key = _blob_storage_key(str(table.workspace_id), table.table_id, row.row_id, column_id)
    try:
        async with s3_client() as s3:
            await s3.put_object(
                Bucket=settings.minio.bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="text/markdown",
            )
        await repo.update_blob(
            row,
            column_id,
            BlobCellMetadata(
                key=key,
                filename=(
                    row.row_data.get(column_id, {}).get("filename")
                    if isinstance(row.row_data.get(column_id), dict)
                    else f"{column['name']}.md"
                )
                or f"{column['name']}.md",
                content_type="text/markdown",
                size=len(body.encode("utf-8")),
            ).model_dump(),
            updated_by=user.user_id,
        )
        return body
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


# --------------------------------------------------
# BLOB CELLS (one file per blob-type column)
# --------------------------------------------------


@router.get(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}/doc",
    response_class=PlainTextResponse,
    summary="Read an addressed Markdown blob cell",
    description="""Use only with a `blob` column whose `options.kind` is `doc`.

Returns an empty text body when the cell has no object yet. New clients should use this addressed route rather than the legacy row `/doc` routes.""",
)
async def get_doc_blob_cell(
    table_id: str,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> str:
    """Read a markdown document stored in one explicitly addressed blob cell."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_doc_column(table, column_id, session)
    row = await RowRepository(session).get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    key = _cell_blob_key(row.row_data.get(column_id))
    if not key:
        return ""
    content = await _read_blob_content(key)
    if content is None:
        return ""
    return content.decode("utf-8")


@router.put(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}/doc",
    response_model=BlobCellMetadata,
    summary="Replace an addressed Markdown blob cell",
    description="""Use only with a `blob` column whose `options.kind` is `doc`.

Send the Markdown text as the request body (`Content-Type: text/plain` or `text/markdown`). The response descriptor is also written to `row_data[column_id]`. Repeating this request replaces the prior document.""",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "text/plain": {
                    "schema": {"type": "string"},
                    "example": "# Design notes\\n\\nInitial draft.\\n",
                }
            },
        }
    },
)
async def put_doc_blob_cell(
    table_id: str,
    row_id: int,
    column_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> BlobCellMetadata:
    """Write a markdown document to one explicitly addressed blob cell."""
    body = (await request.body()).decode("utf-8")
    table = await _get_table_for_member(table_id, user, session)
    column = await _get_doc_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    current_metadata = row.row_data.get(column_id)
    filename = (
        current_metadata.get("filename")
        if isinstance(current_metadata, dict) and isinstance(current_metadata.get("filename"), str)
        else f"{column['name']}.md"
    )
    metadata = BlobCellMetadata(
        key=_blob_storage_key(str(table.workspace_id), table.table_id, row.row_id, column_id),
        filename=filename,
        content_type="text/markdown",
        size=len(body.encode("utf-8")),
    )
    try:
        async with s3_client() as s3:
            await s3.put_object(
                Bucket=settings.minio.bucket,
                Key=metadata.key,
                Body=body.encode("utf-8"),
                ContentType=metadata.content_type,
            )
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e
    await repo.update_blob(row, column_id, metadata.model_dump(), updated_by=user.user_id)
    return metadata


@router.put(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}",
    response_model=BlobCellMetadata,
    summary="Upload or replace one arbitrary blob file",
    description="""Upload one `multipart/form-data` field named `file` to any `blob` column.

The column's `kind` and `accept` options are UI hints, not server-side MIME restrictions: `file` columns may store ZIP or any other binary. The uploaded object replaces the cell's prior object; the returned descriptor is persisted in `row_data[column_id]`. Each cell holds one file only.""",
)
async def put_blob_cell(
    table_id: str,
    row_id: int,
    column_id: str,
    file: Annotated[UploadFile, File(description="The single file stored in this blob cell")],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> BlobCellMetadata:
    """Upload the one file stored by a blob column and persist its metadata in row_data."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_blob_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    content = await file.read()
    metadata = BlobCellMetadata(
        key=_blob_storage_key(str(table.workspace_id), table.table_id, row.row_id, column_id),
        filename=file.filename or "blob",
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
    )
    try:
        async with s3_client() as s3:
            await s3.put_object(
                Bucket=settings.minio.bucket,
                Key=metadata.key,
                Body=content,
                ContentType=metadata.content_type,
            )
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e

    await repo.update_blob(row, column_id, metadata.model_dump(), updated_by=user.user_id)
    return metadata


@router.get(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}",
    summary="Download one blob cell's original bytes",
    description="""Downloads the object described by `row_data[column_id]`.

The response preserves the stored MIME type and sends an attachment filename. Returns 404 when the cell is empty or its object no longer exists.""",
)
async def get_blob_cell(
    table_id: str,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> StreamingResponse:
    """Download the file currently stored in a blob column cell."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_blob_column(table, column_id, session)
    row = await RowRepository(session).get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    metadata = row.row_data.get(column_id)
    if not isinstance(metadata, dict) or not isinstance(metadata.get("key"), str):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found")

    try:
        async with s3_client() as s3:
            response = await s3.get_object(Bucket=settings.minio.bucket, Key=metadata["key"])
            content = await response["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found") from e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e

    filename = str(metadata.get("filename") or "blob")
    return StreamingResponse(
        BytesIO(content),
        media_type=str(metadata.get("content_type") or "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.delete(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one blob cell",
    description="Deletes the stored object and clears that cell's metadata. The cell remains available for a later upload.",
)
async def delete_blob_cell(
    table_id: str,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a blob object's immutable storage key and clear its row_data metadata."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_blob_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    metadata = row.row_data.get(column_id)
    if not isinstance(metadata, dict) or not isinstance(metadata.get("key"), str):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found")

    try:
        async with s3_client() as s3:
            await s3.delete_object(Bucket=settings.minio.bucket, Key=metadata["key"])
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e

    await repo.update_blob(row, column_id, {}, updated_by=user.user_id)


@router.delete("/tables/{table_id}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    table_id: str,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a row by row_id (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.workspace_id, table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    # Delete MinIO objects for storage-backed columns (best-effort).
    columns = (await TableViewRepository(session).get_tables_schema(table.workspace_id, table.table_id))["columns"]
    storage_cols = [c for c in columns if c.get("type") == "blob"]
    for storage_col in storage_cols:
        cell_value = row.row_data.get(storage_col["column_id"])
        minio_key = cell_value.get("key") if isinstance(cell_value, dict) else cell_value
        if minio_key:
            try:
                async with s3_client() as s3:
                    await s3.delete_object(Bucket=settings.minio.bucket, Key=str(minio_key))
            except Exception:
                pass
    await repo.delete(row=row)
