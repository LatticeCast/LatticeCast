"""
E2E Authentication Tests for Lattice Cast Backend

Usage:
    1. Create a tokens.json file in the same directory with:
       {
           "admin": "ya29...",      // posetmage@gmail.com (admin)
           "user": "ya29...",       // homunmage@gmail.com (to be added as user)
           "unregistered": "ya29..."  // latticemage@gmail.com (not in DB)
       }
    2. Run: python -m pytest tests/e2e_auth_test.py -v
       Or:  python tests/e2e_auth_test.py
"""

import json
import os
import httpx
import pytest
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
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


class TestHealthCheck:
    def test_status_endpoint(self, client):
        """Test /status endpoint is accessible"""
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "valkey" in data
        assert "db" in data


class TestAdminAuth:
    def test_admin_can_access_me(self, client, tokens):
        """Admin user can access /api/login/me"""
        resp = client.get(
            "/api/login/me",
            headers={"Authorization": f"Bearer {tokens['admin']}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        assert data["provider"] == "google"
        assert "email" in data
        print(f"✓ Admin: {data['email']} (role={data['role']})")

    def test_admin_can_list_users(self, client, tokens):
        """Admin can list all users"""
        resp = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {tokens['admin']}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "total" in data
        print(f"✓ Total users: {data['total']}")


class TestUserManagement:
    def test_admin_can_create_user(self, client, tokens):
        """Admin can create a new user"""
        # First try to delete if exists (cleanup from previous run)
        client.delete(
            "/admin/users/homunmage@gmail.com",
            headers={"Authorization": f"Bearer {tokens['admin']}"}
        )

        # Create user
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
            json={"id": "homunmage@gmail.com", "role": "user"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "homunmage@gmail.com"
        assert data["role"] == "user"
        print(f"✓ Created user: {data['id']}")

    def test_registered_user_can_access_me(self, client, tokens):
        """Registered user can access /api/login/me"""
        resp = client.get(
            "/api/login/me",
            headers={"Authorization": f"Bearer {tokens['user']}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["email"] == "homunmage@gmail.com"
        print(f"✓ User: {data['email']} (role={data['role']})")

    def test_registered_user_cannot_access_admin(self, client, tokens):
        """Regular user cannot access admin endpoints"""
        resp = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {tokens['user']}"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        print("✓ User correctly denied admin access")


class TestUnregisteredUser:
    def test_unregistered_user_rejected(self, client, tokens):
        """Unregistered user gets 403 on /me"""
        resp = client.get(
            "/api/login/me",
            headers={"Authorization": f"Bearer {tokens['unregistered']}"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "User not registered"
        print("✓ Unregistered user correctly rejected")

    def test_unregistered_user_cannot_access_admin(self, client, tokens):
        """Unregistered user cannot access admin endpoints"""
        resp = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {tokens['unregistered']}"}
        )
        assert resp.status_code == 403
        print("✓ Unregistered user correctly denied admin access")


class TestInvalidAuth:
    def test_missing_token_rejected(self, client):
        """Request without token is rejected"""
        resp = client.get("/api/login/me")
        assert resp.status_code == 401
        assert "Missing Authorization header" in resp.json()["detail"]
        print("✓ Missing token correctly rejected")

    def test_invalid_token_rejected(self, client):
        """Request with invalid token is rejected"""
        resp = client.get(
            "/api/login/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert resp.status_code == 401
        print("✓ Invalid token correctly rejected")


def run_all_tests():
    """Run all tests manually (without pytest)"""
    tokens = load_tokens()
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    print("\n" + "="*60)
    print("E2E Authentication Tests")
    print("="*60)

    # Health check
    print("\n--- Health Check ---")
    resp = client.get("/status")
    assert resp.status_code == 200, f"Status check failed: {resp.text}"
    print(f"✓ Backend status: {resp.json()}")

    # Admin tests
    print("\n--- Admin Tests ---")
    resp = client.get("/api/login/me", headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert resp.status_code == 200, f"Admin /me failed: {resp.text}"
    admin_data = resp.json()
    assert admin_data["role"] == "admin"
    print(f"✓ Admin authenticated: {admin_data['email']} (role={admin_data['role']})")

    # Create user
    print("\n--- User Management ---")
    # Cleanup first
    client.delete("/admin/users/homunmage@gmail.com", headers={"Authorization": f"Bearer {tokens['admin']}"})

    resp = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
        json={"id": "homunmage@gmail.com", "role": "user"}
    )
    assert resp.status_code == 201, f"Create user failed: {resp.text}"
    print(f"✓ Created user: homunmage@gmail.com")

    # Test registered user
    resp = client.get("/api/login/me", headers={"Authorization": f"Bearer {tokens['user']}"})
    assert resp.status_code == 200, f"User /me failed: {resp.text}"
    user_data = resp.json()
    print(f"✓ User authenticated: {user_data['email']} (role={user_data['role']})")

    # Test user cannot access admin
    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {tokens['user']}"})
    assert resp.status_code == 403, f"User should not access admin: {resp.text}"
    print("✓ User correctly denied admin access")

    # Test unregistered user
    print("\n--- Unregistered User Tests ---")
    resp = client.get("/api/login/me", headers={"Authorization": f"Bearer {tokens['unregistered']}"})
    assert resp.status_code == 403, f"Unregistered should be rejected: {resp.text}"
    print("✓ Unregistered user correctly rejected (403)")

    # Test invalid auth
    print("\n--- Invalid Auth Tests ---")
    resp = client.get("/api/login/me")
    assert resp.status_code == 401
    print("✓ Missing token rejected (401)")

    resp = client.get("/api/login/me", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401
    print("✓ Invalid token rejected (401)")

    # List users
    print("\n--- Final State ---")
    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {tokens['admin']}"})
    users = resp.json()
    print(f"✓ Total users in DB: {users['total']}")
    for u in users['users']:
        print(f"  - {u['id']} (role={u['role']})")

    print("\n" + "="*60)
    print("All tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
