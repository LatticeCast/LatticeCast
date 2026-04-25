"""
E2E Storage Tests for Lattice Cast Backend

Tests the S3-compatible storage endpoints:
- Admin can r/w any path, list all files
- User files are prefixed with UUID (first 20 chars, no dashes)
- User sees /file.txt but stored as {uuid_prefix}/file.txt

Usage:
    1. Ensure tokens.json exists with valid tokens
    2. Run: python tests/e2e_storage_test.py
       Or:  python -m pytest tests/e2e_storage_test.py -v
"""

import io
import json
import os
from pathlib import Path

import httpx
import pytest

BACKEND_PORT = os.environ.get("BACKEND_PORT", "13491")
BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{BACKEND_PORT}")
TOKENS_FILE = Path(__file__).parent / "tokens.json"


def load_tokens() -> dict:
    """Load tokens from tokens.json"""
    if not TOKENS_FILE.exists():
        pytest.skip(f"tokens.json not found at {TOKENS_FILE}")
    with open(TOKENS_FILE) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def tokens():
    return load_tokens()


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture(scope="module")
def user_uuid(client, tokens):
    """Get the user's UUID from the database"""
    # First ensure user exists
    client.delete("/admin/users/homunmage@gmail.com", headers={"Authorization": f"Bearer {tokens['admin']}"})
    resp = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
        json={"id": "homunmage@gmail.com", "role": "user"},
    )
    assert resp.status_code == 201
    return resp.json()["uuid"]


class TestStorageHealth:
    def test_settings_includes_minio(self, client):
        """Test /settings includes MinIO configuration"""
        resp = client.get("/status")
        assert resp.status_code == 200

        resp = client.get("/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "minio_endpoint" in data
        assert "minio_bucket" in data
        print(f"✓ MinIO endpoint: {data['minio_endpoint']}")
        print(f"✓ MinIO bucket: {data['minio_bucket']}")


class TestAdminStorage:
    def test_admin_can_upload_file(self, client, tokens):
        """Admin can upload a file to any path"""
        content = b"Hello from admin test!"
        files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}

        resp = client.put(
            "/api/storage/file/admin-test/hello.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
            files=files,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "admin-test/hello.txt"
        assert data["size"] == len(content)
        print(f"✓ Admin uploaded: {data['key']} ({data['size']} bytes)")

    def test_admin_can_list_all_files(self, client, tokens):
        """Admin can list all files"""
        resp = client.get(
            "/api/storage/admin/files",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        print(f"✓ Admin sees {len(data['files'])} files")
        for f in data["files"]:
            print(f"  - {f['key']} ({f['size']} bytes)")

    def test_admin_can_download_file(self, client, tokens):
        """Admin can download any file"""
        resp = client.get(
            "/api/storage/file/admin-test/hello.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200
        assert resp.content == b"Hello from admin test!"
        print("✓ Admin downloaded file successfully")

    def test_admin_can_delete_file(self, client, tokens):
        """Admin can delete any file"""
        resp = client.delete(
            "/api/storage/file/admin-test/hello.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "admin-test/hello.txt"
        print("✓ Admin deleted file successfully")


class TestUserStorage:
    def test_user_can_upload_file(self, client, tokens, user_uuid):
        """User can upload a file (prefixed with UUID)"""
        content = b"Hello from user test!"
        files = {"file": ("user-file.txt", io.BytesIO(content), "text/plain")}

        resp = client.put(
            "/api/storage/file/my-folder/user-file.txt",
            headers={"Authorization": f"Bearer {tokens['user']}"},
            files=files,
        )
        assert resp.status_code == 200
        data = resp.json()
        # User sees their own path (without UUID prefix)
        assert data["key"] == "my-folder/user-file.txt"
        print(f"✓ User uploaded: {data['key']} ({data['size']} bytes)")

        # Get user's UUID prefix
        uuid_prefix = user_uuid.replace("-", "")[:20]
        print(f"✓ User UUID prefix: {uuid_prefix}")

    def test_user_can_list_own_files(self, client, tokens):
        """User can list their own files"""
        resp = client.get(
            "/api/storage/files",
            headers={"Authorization": f"Bearer {tokens['user']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        print(f"✓ User sees {len(data['files'])} files")
        for f in data["files"]:
            # User should see paths without UUID prefix
            assert not f["key"].startswith(f["key"][:20])  # Should not start with UUID
            print(f"  - {f['key']} ({f['size']} bytes)")

    def test_user_can_download_own_file(self, client, tokens):
        """User can download their own files"""
        resp = client.get(
            "/api/storage/file/my-folder/user-file.txt",
            headers={"Authorization": f"Bearer {tokens['user']}"},
        )
        assert resp.status_code == 200
        assert resp.content == b"Hello from user test!"
        print("✓ User downloaded own file successfully")

    def test_user_cannot_access_admin_files(self, client, tokens):
        """User cannot access files outside their prefix"""
        # First, admin uploads a file
        content = b"Admin secret file"
        files = {"file": ("secret.txt", io.BytesIO(content), "text/plain")}
        client.put(
            "/api/storage/file/other-user/secret.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
            files=files,
        )

        # User tries to access it - should get 404 (file not in their prefix)
        resp = client.get(
            "/api/storage/file/other-user/secret.txt",
            headers={"Authorization": f"Bearer {tokens['user']}"},
        )
        assert resp.status_code == 404
        print("✓ User correctly denied access to other files")

        # Cleanup
        client.delete(
            "/api/storage/file/other-user/secret.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )

    def test_user_can_delete_own_file(self, client, tokens):
        """User can delete their own files"""
        resp = client.delete(
            "/api/storage/file/my-folder/user-file.txt",
            headers={"Authorization": f"Bearer {tokens['user']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "my-folder/user-file.txt"
        print("✓ User deleted own file successfully")


class TestAdminSeesUserFiles:
    def test_admin_sees_user_files_with_prefix(self, client, tokens, user_uuid):
        """Admin sees user files with full path including UUID prefix"""
        # User uploads a file
        content = b"User file for admin visibility test"
        files = {"file": ("visible.txt", io.BytesIO(content), "text/plain")}
        resp = client.put(
            "/api/storage/file/test/visible.txt",
            headers={"Authorization": f"Bearer {tokens['user']}"},
            files=files,
        )
        assert resp.status_code == 200

        # Admin lists all files
        resp = client.get(
            "/api/storage/admin/files",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Find the user's file - should have UUID prefix
        uuid_prefix = user_uuid.replace("-", "")[:20]
        expected_key = f"{uuid_prefix}/test/visible.txt"

        found = False
        for f in data["files"]:
            if f["key"] == expected_key:
                found = True
                print(f"✓ Admin sees user file with full path: {f['key']}")
                break

        assert found, f"Expected to find {expected_key} in admin file list"

        # Admin can also download it directly
        resp = client.get(
            f"/api/storage/file/{uuid_prefix}/test/visible.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200
        assert resp.content == content
        print("✓ Admin can download user file using full path")

        # Cleanup
        resp = client.delete(
            f"/api/storage/file/{uuid_prefix}/test/visible.txt",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert resp.status_code == 200


class TestUnregisteredUser:
    def test_unregistered_cannot_access_storage(self, client, tokens):
        """Unregistered user cannot access storage"""
        resp = client.get(
            "/api/storage/files",
            headers={"Authorization": f"Bearer {tokens['unregistered']}"},
        )
        assert resp.status_code == 403
        print("✓ Unregistered user correctly denied storage access")


class TestPathSecurity:
    def test_directory_traversal_blocked(self, client, tokens):
        """Directory traversal attempts are blocked"""
        resp = client.get(
            "/api/storage/file/../../../etc/passwd",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        # Accept 400 (explicit block) or 404 (path normalized away)
        assert resp.status_code in (400, 404)
        print("✓ Directory traversal correctly blocked")


def run_all_tests():
    """Run all tests manually (without pytest)"""
    tokens = load_tokens()
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    print("\n" + "=" * 60)
    print("E2E Storage Tests")
    print("=" * 60)

    # Health check
    print("\n--- Health Check ---")
    resp = client.get("/status")
    assert resp.status_code == 200
    print(f"✓ Backend status: {resp.json()}")

    resp = client.get("/settings")
    data = resp.json()
    print(f"✓ MinIO endpoint: {data.get('minio_endpoint', 'N/A')}")
    print(f"✓ MinIO bucket: {data.get('minio_bucket', 'N/A')}")

    # Ensure user exists
    print("\n--- Setup ---")
    client.delete("/admin/users/homunmage@gmail.com", headers={"Authorization": f"Bearer {tokens['admin']}"})
    resp = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
        json={"id": "homunmage@gmail.com", "role": "user"},
    )
    assert resp.status_code == 201
    user_uuid = resp.json()["uuid"]
    uuid_prefix = user_uuid.replace("-", "")[:20]
    print(f"✓ Created user with UUID prefix: {uuid_prefix}")

    # Admin tests
    print("\n--- Admin Storage Tests ---")
    content = b"Hello from admin!"
    files = {"file": ("admin.txt", io.BytesIO(content), "text/plain")}
    resp = client.put(
        "/api/storage/file/admin-test/admin.txt",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
        files=files,
    )
    assert resp.status_code == 200
    print("✓ Admin uploaded: admin-test/admin.txt")

    resp = client.get(
        "/api/storage/admin/files",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    print(f"✓ Admin listed {len(resp.json()['files'])} files")

    resp = client.delete(
        "/api/storage/file/admin-test/admin.txt",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert resp.status_code == 200
    print("✓ Admin deleted file")

    # User tests
    print("\n--- User Storage Tests ---")
    content = b"Hello from user!"
    files = {"file": ("user.txt", io.BytesIO(content), "text/plain")}
    resp = client.put(
        "/api/storage/file/my-data/user.txt",
        headers={"Authorization": f"Bearer {tokens['user']}"},
        files=files,
    )
    assert resp.status_code == 200
    print("✓ User uploaded: my-data/user.txt")

    resp = client.get(
        "/api/storage/files",
        headers={"Authorization": f"Bearer {tokens['user']}"},
    )
    assert resp.status_code == 200
    user_files = resp.json()["files"]
    print(f"✓ User sees {len(user_files)} file(s)")
    for f in user_files:
        print(f"  - {f['key']}")

    # Admin sees user file with prefix
    resp = client.get(
        "/api/storage/admin/files",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    admin_files = resp.json()["files"]
    user_file_path = f"{uuid_prefix}/my-data/user.txt"
    found = any(f["key"] == user_file_path for f in admin_files)
    assert found, f"Admin should see {user_file_path}"
    print(f"✓ Admin sees user file as: {user_file_path}")

    # User deletes own file
    resp = client.delete(
        "/api/storage/file/my-data/user.txt",
        headers={"Authorization": f"Bearer {tokens['user']}"},
    )
    assert resp.status_code == 200
    print("✓ User deleted own file")

    # Unregistered user test
    print("\n--- Unregistered User Test ---")
    resp = client.get(
        "/api/storage/files",
        headers={"Authorization": f"Bearer {tokens['unregistered']}"},
    )
    assert resp.status_code == 403
    print("✓ Unregistered user denied (403)")

    # Security test
    print("\n--- Security Tests ---")
    resp = client.get(
        "/api/storage/file/../../../etc/passwd",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    # Accept 400 (explicit block) or 404 (path normalized away)
    assert resp.status_code in (400, 404)
    print("✓ Directory traversal blocked")

    print("\n" + "=" * 60)
    print("All storage tests passed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_all_tests()
