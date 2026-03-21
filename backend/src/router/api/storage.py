# src/router/api/storage.py
"""
Storage API endpoints using S3-compatible interface.

- Admin: can r/w any path, list all files
- User: files are prefixed with UUID (first 20 chars, no dashes)
        user sees "/file.txt" but stored as "{uuid_prefix}/file.txt"
"""

from io import BytesIO
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.settings import settings
from config.storage import get_s3_client
from middleware.auth import get_current_user, require_admin
from models.user import User

router = APIRouter(prefix="/storage", tags=["storage"])


# --------------------------------------------------
# HELPERS
# --------------------------------------------------


def get_user_prefix(user: User) -> str:
    """Get user's storage prefix (first 20 chars of UUID, no dashes)"""
    return user.user_id.replace("@", "_at_").replace(".", "_")[:20]


def normalize_path(path: str) -> str:
    """Normalize path: remove leading slashes, prevent directory traversal"""
    # Remove leading slashes
    path = path.lstrip("/")
    # Prevent directory traversal
    if ".." in path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path: directory traversal not allowed"
        )
    return path


def get_full_path(user: User, path: str) -> str:
    """Get full storage path for user"""
    path = normalize_path(path)
    if user.role == "admin":
        return path
    prefix = get_user_prefix(user)
    return f"{prefix}/{path}" if path else prefix


# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------


class FileInfo(BaseModel):
    """File metadata"""

    key: str = Field(..., description="File path/key")
    size: int = Field(..., description="File size in bytes")
    last_modified: str = Field(..., description="Last modified timestamp")


class FileListResponse(BaseModel):
    """List of files"""

    files: list[FileInfo]
    prefix: str = Field(..., description="Current prefix/directory")
    truncated: bool = Field(default=False, description="Whether there are more files")


class UploadResponse(BaseModel):
    """Upload response"""

    key: str = Field(..., description="Uploaded file path")
    size: int = Field(..., description="File size in bytes")


class DeleteResponse(BaseModel):
    """Delete response"""

    deleted: str = Field(..., description="Deleted file path")


# --------------------------------------------------
# USER ENDPOINTS
# --------------------------------------------------


@router.get("/files", response_model=FileListResponse)
async def list_files(
    user: User = Depends(get_current_user),
    prefix: str = Query(default="", description="Directory prefix to list"),
    max_keys: int = Query(default=1000, ge=1, le=10000, description="Maximum files to return"),
):
    """
    List files in storage.
    - Admin: lists all files or files under specified prefix
    - User: lists only files under user's UUID prefix
    """
    client = get_s3_client()
    bucket = settings.minio.bucket

    # Build full prefix
    full_prefix = get_full_path(user, prefix)
    # Ensure prefix ends with / for directory listing (unless empty)
    if full_prefix and not full_prefix.endswith("/"):
        full_prefix += "/"
    # For root listing, don't add trailing slash
    if not prefix and user.role != "admin":
        full_prefix = get_user_prefix(user) + "/"

    try:
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=full_prefix if full_prefix != "/" else "",
            MaxKeys=max_keys,
        )

        files = []
        user_prefix = get_user_prefix(user) if user.role != "admin" else ""

        for obj in response.get("Contents", []):
            key = obj["Key"]
            # For non-admin users, strip the UUID prefix from displayed key
            display_key = key
            if user.role != "admin" and key.startswith(user_prefix + "/"):
                display_key = key[len(user_prefix) + 1 :]

            files.append(
                FileInfo(
                    key=display_key,
                    size=obj["Size"],
                    last_modified=obj["LastModified"].isoformat(),
                )
            )

        return FileListResponse(
            files=files,
            prefix=prefix,
            truncated=response.get("IsTruncated", False),
        )

    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Storage error: {e.response['Error']['Message']}"
        ) from e


@router.get("/file/{path:path}")
async def download_file(
    path: str,
    user: User = Depends(get_current_user),
):
    """
    Download a file.
    - Admin: can download any file
    - User: can only download files under their UUID prefix
    """
    client = get_s3_client()
    bucket = settings.minio.bucket
    full_path = get_full_path(user, path)

    try:
        response = client.get_object(Bucket=bucket, Key=full_path)
        content = response["Body"].read()

        # Determine content type
        content_type = response.get("ContentType", "application/octet-stream")

        # Get filename from path
        filename = path.split("/")[-1] if "/" in path else path

        return StreamingResponse(
            BytesIO(content),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in ("404", "NoSuchKey"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Storage error: {e.response['Error']['Message']}"
        ) from e


@router.put("/file/{path:path}", response_model=UploadResponse)
async def upload_file(
    path: str,
    file: Annotated[UploadFile, File(description="File to upload")],
    user: User = Depends(get_current_user),
):
    """
    Upload a file.
    - Admin: can upload to any path
    - User: uploads are prefixed with user's UUID
    """
    client = get_s3_client()
    bucket = settings.minio.bucket
    full_path = get_full_path(user, path)

    try:
        content = await file.read()
        content_type = file.content_type or "application/octet-stream"

        client.put_object(
            Bucket=bucket,
            Key=full_path,
            Body=content,
            ContentType=content_type,
        )

        return UploadResponse(
            key=path,  # Return user-visible path
            size=len(content),
        )

    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Storage error: {e.response['Error']['Message']}"
        ) from e


@router.delete("/file/{path:path}", response_model=DeleteResponse)
async def delete_file(
    path: str,
    user: User = Depends(get_current_user),
):
    """
    Delete a file.
    - Admin: can delete any file
    - User: can only delete files under their UUID prefix
    """
    client = get_s3_client()
    bucket = settings.minio.bucket
    full_path = get_full_path(user, path)

    try:
        # Check if file exists first
        client.head_object(Bucket=bucket, Key=full_path)

        # Delete the file
        client.delete_object(Bucket=bucket, Key=full_path)

        return DeleteResponse(deleted=path)

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in ("404", "NoSuchKey"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Storage error: {e.response['Error']['Message']}"
        ) from e


# --------------------------------------------------
# ADMIN ENDPOINTS
# --------------------------------------------------


@router.get("/admin/files", response_model=FileListResponse)
async def admin_list_all_files(
    user: User = Depends(require_admin),
    prefix: str = Query(default="", description="Directory prefix to list"),
    max_keys: int = Query(default=1000, ge=1, le=10000, description="Maximum files to return"),
):
    """
    Admin: List all files in storage with full paths.
    """
    client = get_s3_client()
    bucket = settings.minio.bucket

    try:
        list_prefix = normalize_path(prefix)
        if list_prefix and not list_prefix.endswith("/"):
            list_prefix += "/"

        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=list_prefix if list_prefix != "/" else "",
            MaxKeys=max_keys,
        )

        files = [
            FileInfo(
                key=obj["Key"],
                size=obj["Size"],
                last_modified=obj["LastModified"].isoformat(),
            )
            for obj in response.get("Contents", [])
        ]

        return FileListResponse(
            files=files,
            prefix=prefix,
            truncated=response.get("IsTruncated", False),
        )

    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Storage error: {e.response['Error']['Message']}"
        ) from e
