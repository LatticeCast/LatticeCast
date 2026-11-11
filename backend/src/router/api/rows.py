# router/api/rows.py

import json
from io import BytesIO
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from config.storage import s3_client
from middleware.auth import get_current_user, get_rls_session
from models.row import RowCreate, RowPut, RowQueryResponse, RowResponse, RowUpdate
from models.user import User
from repository.row import RowRepository
from repository.table_view import TableViewRepository
from services.blob_objects import queue_orphan_upload
from util import logger
from util.pg_errors import http_error_for

from .tables._shared import _get_table_for_member

router = APIRouter(tags=["rows"])


class BlobCellMetadata(BaseModel):
    """Descriptor stored in ``row_data[column_id]``; the object body is in S3-compatible storage."""

    key: str = Field(description="Server-owned object key; clients must not construct or edit it.")
    filename: str = Field(description="Original upload filename or generated Markdown filename.")
    content_type: str = Field(description="Stored MIME type, such as application/zip.")
    size: int = Field(description="Object size in bytes.", ge=0)


def _blob_storage_key(workspace_id: str, table_id: int, row_id: int, column_id: str) -> str:
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


# --------------------------------------------------
# ROWS (nested under table for create/list)
# --------------------------------------------------


def _parse_row_query_ids(raw: str, kind: str) -> list[int] | list[UUID]:
    try:
        values = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{kind} must be a JSON array") from exc
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise HTTPException(status_code=422, detail=f"{kind} must contain 1 to 100 IDs")

    if kind == "table_ids":
        if any(type(value) is not int or not 1 <= value <= 2**63 - 1 for value in values):
            raise HTTPException(status_code=422, detail="table_ids must contain positive bigint IDs")
        return list(dict.fromkeys(values))

    parsed: list[UUID] = []
    for value in values:
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail="workspace_ids must contain UUID strings")
        try:
            parsed.append(UUID(value))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="workspace_ids must contain UUID strings") from exc
    return list(dict.fromkeys(parsed))


@router.get(
    "/rows",
    response_model=RowQueryResponse,
    summary="Query rows across tables or workspaces",
    response_description="RLS-visible rows with optional pagination metadata.",
)
async def query_rows(
    table_ids: str | None = Query(
        default=None,
        description="JSON array of 1-100 positive table IDs, e.g. [12,13]. Supply this or workspace_ids, never both.",
    ),
    workspace_ids: str | None = Query(
        default=None,
        description='JSON array of 1-100 workspace UUID strings, e.g. ["uuid-1","uuid-2"]. Supply this or table_ids.',
    ),
    page: int | None = Query(
        default=None,
        ge=1,
        description="1-based page number. Requires page_size; defaults to 1 when page_size is supplied.",
    ),
    page_size: int | None = Query(
        default=None, ge=1, le=200, description="Rows per page (1-200). Omit to return every matching row."
    ),
    sort_by: Literal["row_id", "table_id", "created_at", "updated_at"] = Query(
        default="row_id", description="System column for ordering. Ties are resolved by table_id and row_id."
    ),
    desc: bool = Query(default=True, description="Sort descending when true; ascending when false."),
    filter_json: str | None = Query(
        default=None,
        description='JSON object matched by row_data @> filter_json, e.g. {"column-uuid":"Osaka"}.',
    ),
    include_total: bool = Query(
        default=False, description="Return the exact matching row count and total pages when true."
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Query rows from exactly one source type.

    IDs that are missing or hidden by RLS contribute no rows. The default order
    is row_id DESC, table_id DESC; row IDs are local to each table. Without
    page_size, the full result is returned, and page, page_size, total_pages
    are null. With page_size, has_more reports whether a next page exists.
    total and total_pages are null unless include_total=true.
    """
    if (table_ids is None) == (workspace_ids is None):
        raise HTTPException(status_code=422, detail="Provide exactly one of table_ids or workspace_ids")
    if page is not None and page_size is None:
        raise HTTPException(status_code=422, detail="page requires page_size")

    selected_tables = _parse_row_query_ids(table_ids, "table_ids") if table_ids is not None else None
    selected_workspaces = _parse_row_query_ids(workspace_ids, "workspace_ids") if workspace_ids is not None else None

    try:
        contains = json.loads(filter_json) if filter_json is not None else {}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="filter_json must be a JSON object") from exc
    if not isinstance(contains, dict):
        raise HTTPException(status_code=422, detail="filter_json must be a JSON object")

    try:
        return await RowRepository(session).query_rows(
            table_ids=selected_tables,
            workspace_ids=selected_workspaces,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            desc=desc,
            filter_json=contains,
            include_total=include_total,
        )
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


@router.post("/tables/{table_id}/rows", response_model=RowResponse, status_code=status.HTTP_201_CREATED)
async def create_row(
    table_id: int,
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


@router.get("/tables/{table_id}/rows", response_model=list[RowResponse], deprecated=True)
async def list_rows(
    table_id: int,
    offset: int = 0,
    limit: int = 100,
    sort: str = "desc",
    filter_json: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Deprecated single-table list. Use GET /rows?table_ids=[id] for new clients."""
    table = await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    if filter_json:
        import json as json_mod

        try:
            contains = json_mod.loads(filter_json)
        except Exception:
            contains = {}
        if contains:
            return await repo.filter_by_jsonb(table.table_id, contains=contains, offset=offset, limit=limit)
    return await repo.list_by_table(table.table_id, offset=offset, limit=limit, sort=sort)


# --------------------------------------------------
# ROWS (nested update/delete by row_id)
# --------------------------------------------------


@router.get("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def get_row(
    table_id: int,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Get a single row by row_id (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    return row


@router.patch("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def patch_row(
    table_id: int,
    row_id: int,
    data: RowUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Merge partial non-blob row data by row_id."""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    try:
        # SELECT permits readers; the update function otherwise reports an
        # RLS-denied write as a generic "row not found" database error.
        row = await repo.lock_for_write(table.table_id, row_id)
        return await repo.patch_row(workspace_id=table.workspace_id, row=row, data=data, updated_by=user.user_id)
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


@router.put("/tables/{table_id}/rows/{row_id}", response_model=RowResponse)
async def put_row(
    table_id: int,
    row_id: int,
    data: RowPut,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Replace all non-blob row data by row_id; blob metadata is preserved."""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    try:
        row = await repo.lock_for_write(table.table_id, row_id)
        return await repo.put_row(workspace_id=table.workspace_id, row=row, data=data, updated_by=user.user_id)
    except DBAPIError as exc:
        await session.rollback()
        raise (http_error_for(exc) or exc) from exc


# --------------------------------------------------
# BLOB CELLS (one file per blob-type column)
# --------------------------------------------------


@router.put(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}",
    response_model=BlobCellMetadata,
    summary="Upload or replace one arbitrary blob file",
    description="""Upload one `multipart/form-data` field named `file` to any `blob` column.

The column's `kind` and `accept` options are UI hints, not server-side MIME restrictions: `file` columns may store ZIP or any other binary. The uploaded object replaces the cell's prior object; the returned descriptor is persisted in `row_data[column_id]`. Each cell holds one file only.""",
)
async def put_blob_cell(
    table_id: int,
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
    resolved_table_id = table.table_id
    workspace_id = table.workspace_id
    actor_id = user.user_id
    row = await repo.get_by_number(resolved_table_id, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    writable = await session.execute(
        text("SELECT :tid IN (SELECT public.current_user_tables('write'))"),
        {"tid": resolved_table_id},
    )
    if not writable.scalar_one():
        raise HTTPException(status_code=403, detail="Row write permission required")
    content = await file.read()
    metadata = BlobCellMetadata(
        key=f"{_blob_storage_key(str(workspace_id), resolved_table_id, row_id, column_id)}/{uuid4().hex}",
        filename=file.filename or "blob",
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
    )
    # Close the RLS read transaction before contacting storage. No row or
    # table lock (or idle DB transaction) may span the S3 request.
    await session.rollback()
    upload_started = False
    try:
        async with s3_client() as s3:
            upload_started = True
            await s3.put_object(
                Bucket=settings.blob.bucket,
                Key=metadata.key,
                Body=content,
                ContentType=metadata.content_type,
            )
        # Recheck after the upload: the workspace, row, column, or permission
        # may have changed while S3 was slow. Nothing is locked here — the
        # single UPDATE inside update_blob_cell takes the row lock for as long
        # as that statement runs and raises if the row is gone, so no lock and
        # no open transaction ever spans the storage request. Registration and
        # publication commit together, so cleanup never sees an unreferenced
        # live key.
        current_table = await _get_table_for_member(resolved_table_id, user, session)
        await _get_blob_column(current_table, column_id, session)
        await session.execute(
            text("SELECT public.register_blob_object(:ws, :tid, :rid, :cid, :key)"),
            {"ws": str(workspace_id), "tid": resolved_table_id, "rid": row_id, "cid": column_id, "key": metadata.key},
        )
        await repo.update_blob(
            workspace_id, resolved_table_id, row_id, column_id, metadata.model_dump(), updated_by=actor_id, commit=False
        )
        await session.commit()
    except BaseException as exc:
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.warn(f"Blob upload transaction rollback failed: {rollback_error}")
        if upload_started:
            try:
                await queue_orphan_upload(metadata.key)
            except Exception as queue_error:
                logger.warn(f"Failed to queue orphan blob {metadata.key}: {queue_error}")
                try:
                    async with s3_client() as s3:
                        await s3.delete_object(Bucket=settings.blob.bucket, Key=metadata.key)
                except Exception as delete_error:
                    logger.warn(f"Failed to delete orphan blob {metadata.key}: {delete_error}")
        if isinstance(exc, ClientError):
            raise HTTPException(status_code=500, detail="Storage error") from exc
        if isinstance(exc, DBAPIError):
            raise (http_error_for(exc) or exc) from exc
        raise
    return metadata


@router.get(
    "/tables/{table_id}/rows/{row_id}/blob/{column_id}",
    summary="Download one blob cell's original bytes",
    description="""Downloads the object described by `row_data[column_id]`.

The response preserves the stored MIME type and sends an attachment filename. Returns 404 when the cell is empty or its object no longer exists.""",
)
async def get_blob_cell(
    table_id: int,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> StreamingResponse:
    """Download the file currently stored in a blob column cell."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_blob_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    for _ in range(4):
        metadata = row.row_data.get(column_id)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("key"), str):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found")
        ownership = await session.execute(
            text("SELECT public.blob_object_belongs_to_cell(:key, :ws, :tid, :rid, :cid)"),
            {
                "key": metadata["key"],
                "ws": str(table.workspace_id),
                "tid": table.table_id,
                "rid": row_id,
                "cid": column_id,
            },
        )
        if not ownership.scalar_one():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found")
        # Protect the selected immutable version from GC, without locking the
        # row: readers can keep using the committed old version during upload.
        await session.execute(
            text("SELECT pg_advisory_xact_lock_shared(hashtextextended(:key, 0))"), {"key": metadata["key"]}
        )
        current = await repo.get_by_number(table.table_id, row_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Row not found")
        if current.row_data.get(column_id) == metadata:
            break
        row = current
    else:
        raise HTTPException(status_code=409, detail="Blob changed during download; retry")

    try:
        async with s3_client() as s3:
            response = await s3.get_object(Bucket=settings.blob.bucket, Key=metadata["key"])
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
    table_id: int,
    row_id: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a blob object's immutable storage key and clear its row_data metadata."""
    table = await _get_table_for_member(table_id, user, session)
    await _get_blob_column(table, column_id, session)
    repo = RowRepository(session)
    row = await repo.lock_for_write(table.table_id, row_id)
    metadata = row.row_data.get(column_id)
    if not isinstance(metadata, dict) or not isinstance(metadata.get("key"), str):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blob not found")

    # Removing the DB reference atomically queues the owned object for cleanup.
    # Storage failures cannot leave a live cell pointing at deleted bytes.
    await repo.update_blob(table.workspace_id, row.table_id, row.row_id, column_id, {}, updated_by=user.user_id)


@router.delete("/tables/{table_id}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    table_id: int,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a row by row_id (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.lock_for_write(table.table_id, row_id)
    await repo.delete(row=row)
