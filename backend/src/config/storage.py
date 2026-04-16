# src/config/storage.py
"""
S3-compatible storage client using aioboto3 (async-native).
Works with MinIO and any S3-compatible storage.

Usage:
    async with s3_client() as s3:
        await s3.put_object(Bucket=..., Key=..., Body=...)
"""

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from config.settings import settings

_session = aioboto3.Session()


def s3_client():
    """
    Return an async context manager that yields an aioboto3 S3 client.
    A new client is created per call — aioboto3 clients are lightweight.

    Example:
        async with s3_client() as s3:
            await s3.put_object(Bucket=..., Key=..., Body=...)
    """
    endpoint_url = f"{'https' if settings.minio.secure else 'http'}://{settings.minio.endpoint}"
    return _session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio.access_key,
        aws_secret_access_key=settings.minio.secret_key,
        config=AioConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


async def ensure_bucket_exists():
    """Ensure the default bucket exists, create if not."""
    bucket = settings.minio.bucket

    async with s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=bucket)
            print(f"✓ Bucket '{bucket}' exists")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                await s3.create_bucket(Bucket=bucket)
                print(f"✓ Created bucket '{bucket}'")
            else:
                print(f"⚠ Bucket check failed: {e}")
                raise
