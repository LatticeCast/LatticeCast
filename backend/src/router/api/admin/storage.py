# router/api/admin/storage.py
"""Storage listing across all users (mounted at /api/v1/admin/storage; admin guard is on the parent)."""

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Query, status

from config.settings import settings
from config.storage import s3_client
from router.api.storage import FileInfo, FileListResponse, normalize_path

router = APIRouter(prefix="/storage", tags=["admin-storage"])


@router.get("/files", response_model=FileListResponse)
async def admin_list_all_files(
    prefix: str = Query(default="", description="Directory prefix to list"),
    max_keys: int = Query(default=1000, ge=1, le=10000, description="Maximum files to return"),
):
    """
    Admin: List all files in storage with full paths.
    """
    bucket = settings.blob.bucket

    try:
        list_prefix = normalize_path(prefix)
        if list_prefix and not list_prefix.endswith("/"):
            list_prefix += "/"

        async with s3_client() as s3:
            response = await s3.list_objects_v2(
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
