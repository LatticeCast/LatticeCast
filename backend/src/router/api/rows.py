# router/api/rows.py

from io import BytesIO
from typing import Annotated
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from config.storage import s3_client
from middleware.auth import get_current_user, get_rls_session
from models.row import RowCreate, RowPut, RowResponse, RowUpdate
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
