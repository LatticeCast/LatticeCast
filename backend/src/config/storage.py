# src/config/storage.py
"""
S3-compatible storage client using boto3.
Works with MinIO and any S3-compatible storage.
"""

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from config.settings import settings

_s3_client = None


def get_s3_client():
    """Get or create S3 client singleton"""
    global _s3_client

    if _s3_client is None:
        endpoint_url = f"{'https' if settings.minio.secure else 'http'}://{settings.minio.endpoint}"

        _s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.minio.access_key,
            aws_secret_access_key=settings.minio.secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # Required for S3 signature
        )

    return _s3_client


async def ensure_bucket_exists():
    """Ensure the default bucket exists, create if not"""
    client = get_s3_client()
    bucket = settings.minio.bucket

    try:
        client.head_bucket(Bucket=bucket)
        print(f"✓ Bucket '{bucket}' exists")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=bucket)
            print(f"✓ Created bucket '{bucket}'")
        else:
            print(f"⚠ Bucket check failed: {e}")
            raise
