# router/api/rows.py

import re
from uuid import UUID

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from config.storage import get_s3_client
from core.db import get_session
from middleware.auth import get_current_user
from models.row import Row, RowCreate, RowResponse, RowUpdate
from models.user import User
from repository.row import RowRepository
from repository.table import TableRepository
from repository.workspace import WorkspaceRepository

router = APIRouter(tags=["rows"])


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
    cols = {c["name"]: c["column_id"] for c in table.columns}
    key_col_id = cols.get("Key", "")
    title_col_id = cols.get("Title", "")
    parent_col_id = cols.get("Parent", "")
    status_col_id = cols.get("Status", "")

    # Inject parent link
    if parent_col_id and re.search(r"<!--\s*\[PARENT-KEY\]", content):
        parent_row_id_str = row.row_data.get(parent_col_id)
        parent_link = ""
        if parent_row_id_str:
            try:
                parent_row = await session.get(Row, UUID(str(parent_row_id_str)))
                if parent_row:
                    p_key = parent_row.row_data.get(key_col_id, "") if key_col_id else ""
                    p_title = parent_row.row_data.get(title_col_id, "") if title_col_id else str(parent_row_id_str)
                    parent_link = f"[{p_key}] {p_title}" if p_key else p_title
            except (ValueError, Exception):
                pass
        if parent_link:
            content = re.sub(r"<!--\s*\[PARENT-KEY\][^>]*-->", parent_link, content)

    # Inject children links
    if parent_col_id and re.search(r"<!--\s*Links to child", content):
        repo = RowRepository(session)
        children = await repo.filter_by_jsonb(table.table_id, {parent_col_id: str(row.row_id)})
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

    return content


async def _get_table_for_member(table_id: str, user: User, session: AsyncSession):
    """Fetch table by UUID or name and verify the current user is a member of its workspace."""
    ws_repo = WorkspaceRepository(session)
    workspaces = await ws_repo.list_by_user(user.user_id)
    workspace_ids = [ws.workspace_id for ws in workspaces]
    table_repo = TableRepository(session)
    table = await table_repo.resolve_table_global(table_id, workspace_ids)
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    if not await ws_repo.is_member(table.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


# --------------------------------------------------
# ROWS (nested under table for create/list)
# --------------------------------------------------


@router.post("/tables/{table_id}/rows", response_model=RowResponse, status_code=status.HTTP_201_CREATED)
async def create_row(
    table_id: str,
    data: RowCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new row in a table (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)

    repo = RowRepository(session)
    row = await repo.create(
        table_id=table.table_id, row_data=data.row_data, created_by=user.user_id, updated_by=user.user_id
    )

    # Auto-create MinIO object and fill cell for every doc-type column
    doc_cols = [c for c in table.columns if c.get("type") == "doc"]
    if doc_cols:
        import json as _json

        from sqlalchemy import text as sa_text

        type_col = next((c for c in table.columns if c.get("name") == "Type"), None)
        title_col = next((c for c in table.columns if c.get("name") == "Title"), None)
        row_type = row.row_data.get(type_col["column_id"], "") if type_col else ""
        row_title = row.row_data.get(title_col["column_id"], "") if title_col else ""
        row_key = f"{row_type}-{row.row_number}" if row_type else str(row.row_number)

        patch: dict = {}
        for doc_col in doc_cols:
            minio_key = f"{table.workspace_id}/{table.table_id}/{row.row_number}.md"
            if row_type in ("epic", "story", "task", "bug"):
                doc_content = _build_doc_template(row_type, row_key, row_title)
            else:
                doc_content = ""
            try:
                get_s3_client().put_object(
                    Bucket=settings.minio.bucket,
                    Key=minio_key,
                    Body=doc_content.encode("utf-8"),
                    ContentType="text/markdown",
                )
            except Exception:
                pass  # best-effort; don't fail row creation
            patch[doc_col["column_id"]] = minio_key
            row.row_data[doc_col["column_id"]] = minio_key

        await session.execute(
            sa_text("""
                UPDATE rows
                SET row_data = row_data || CAST(:patch AS jsonb),
                    updated_at = NOW()
                WHERE table_id = :tid AND row_number = :rn
            """),
            {"patch": _json.dumps(patch), "tid": table.table_id, "rn": row.row_number},
        )
        await session.commit()

    return row


@router.get("/tables/{table_id}/rows", response_model=list[RowResponse])
async def list_rows(
    table_id: str,
    offset: int = 0,
    limit: int = 100,
    sort: str = "desc",
    filter_json: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
            return await repo.filter_by_jsonb(table_id=table.table_id, contains=contains, offset=offset, limit=limit)
    return await repo.list_by_table(table_id=table.table_id, offset=offset, limit=limit, sort=sort)


# --------------------------------------------------
# ROWS (nested update/delete by row_number)
# --------------------------------------------------


@router.put("/tables/{table_id}/rows/{row_number}", response_model=RowResponse)
async def update_row(
    table_id: str,
    row_number: int,
    data: RowUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a row's data by row_number (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    # Silently drop any attempts to change doc-type column values (system-managed)
    doc_col_ids = {c["column_id"] for c in table.columns if c.get("type") == "doc"}
    if doc_col_ids:
        data = RowUpdate(row_data={k: v for k, v in data.row_data.items() if k not in doc_col_ids})
    return await repo.update(row=row, data=data, updated_by=user.user_id)


@router.get("/tables/{table_id}/rows/{row_number}/doc", response_class=PlainTextResponse)
async def get_row_doc(
    table_id: str,
    row_number: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Get markdown doc for a row from MinIO by row_number (returns empty string if not found)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    workspace_id = table.workspace_id
    key = f"{workspace_id}/{table.table_id}/{row.row_number}.md"
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.minio.bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return ""
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e

    if content and (re.search(r"<!--\s*\[PARENT-KEY\]", content) or re.search(r"<!--\s*Links to child", content)):
        content = await _inject_hierarchy(content, table, row, session)

    return content


@router.put("/tables/{table_id}/rows/{row_number}/doc", response_class=PlainTextResponse)
async def put_row_doc(
    table_id: str,
    row_number: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Save markdown doc for a row to MinIO by row_number.
    Accepts text/plain body or multipart/form-data with a 'file' field."""
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
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    workspace_id = table.workspace_id
    key = f"{workspace_id}/{table.table_id}/{row.row_number}.md"
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.minio.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/markdown",
        )
        return body
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


@router.get("/tables/{table_id}/docs-exist")
async def batch_docs_exist(
    table_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[int]]:
    """Return list of row_numbers that have non-empty docs in MinIO (single S3 list, no DB lookup)"""
    table = await _get_table_for_member(table_id, user, session)
    workspace_id = table.workspace_id
    prefix = f"{workspace_id}/{table.table_id}/"
    client = get_s3_client()
    try:
        response = client.list_objects_v2(Bucket=settings.minio.bucket, Prefix=prefix, MaxKeys=1000)
        row_numbers = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".md") and obj.get("Size", 0) > 0:
                filename = key.rsplit("/", 1)[-1].replace(".md", "")
                try:
                    row_numbers.append(int(filename))
                except ValueError:
                    pass
    except ClientError:
        return {"row_numbers": []}

    return {"row_numbers": row_numbers}


@router.get("/tables/{table_id}/rows/{row_number}/col-doc/{column_id}", response_class=PlainTextResponse)
async def get_col_doc(
    table_id: str,
    row_number: int,
    column_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Get markdown doc for a specific column cell from MinIO (returns empty string if not found)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    workspace_id = table.workspace_id
    key = f"{workspace_id}/{table.table_id}/col-{column_id}/{row.row_number}.md"
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.minio.bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return ""
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


@router.put("/tables/{table_id}/rows/{row_number}/col-doc/{column_id}", response_class=PlainTextResponse)
async def put_col_doc(
    table_id: str,
    row_number: int,
    column_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Save markdown doc for a specific column cell to MinIO."""
    body = (await request.body()).decode("utf-8")

    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    workspace_id = table.workspace_id
    key = f"{workspace_id}/{table.table_id}/col-{column_id}/{row.row_number}.md"
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.minio.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/markdown",
        )
        return body
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error") from e


@router.delete("/tables/{table_id}/rows/{row_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    table_id: str,
    row_number: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a row by row_number (user must be a workspace member)"""
    table = await _get_table_for_member(table_id, user, session)
    repo = RowRepository(session)
    row = await repo.get_by_number(table.table_id, row_number)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    # Delete MinIO objects for any doc-type columns (best-effort)
    doc_cols = [c for c in table.columns if c.get("type") == "doc"]
    for doc_col in doc_cols:
        minio_key = row.row_data.get(doc_col["column_id"])
        if minio_key:
            try:
                get_s3_client().delete_object(Bucket=settings.minio.bucket, Key=str(minio_key))
            except Exception:
                pass
    await repo.delete(row=row)
