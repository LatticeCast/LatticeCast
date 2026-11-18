"""Password self-service uses the authenticated RLS identity end to end."""

from __future__ import annotations

import time
from uuid import uuid4

import requests

from e2e_base import BASE, api


def test_password_self_service_is_bound_to_current_user(admin_token):
    suffix = str(int(time.time() * 1000) % 10_000_000)
    user_name = f"pwd_e2e_{suffix}"
    email = f"{user_name}@e2e.local"
    password = "new-e2e-password"

    try:
        response = api(
            "POST",
            "/api/v1/admin/users",
            admin_token,
            json={"email": email, "user_name": user_name, "allow_no_pwd": True},
        )
        assert response.status_code == 201, response.text[:200]

        response = api(
            "POST",
            "/api/v1/login/password",
            None,
            json={"user_name": user_name, "password": "first-login"},
        )
        assert response.status_code == 200, response.text[:200]
        user_token = response.json()["access_token"]

        response = api(
            "PUT",
            "/api/v1/login/me/password",
            user_token,
            json={"new_password": password},
        )
        assert response.status_code == 200, response.text[:200]

        response = api(
            "POST",
            "/api/v1/login/password",
            None,
            json={"user_name": user_name, "password": "wrong-password"},
        )
        assert response.status_code == 401, response.text[:200]

        response = api(
            "POST",
            "/api/v1/login/password",
            None,
            json={"user_name": user_name, "password": password},
        )
        assert response.status_code == 200, response.text[:200]
    finally:
        api("DELETE", f"/api/v1/admin/users/{email}", admin_token)


def test_passwordless_login_requires_an_explicit_allow_no_pwd(admin_token):
    """No password and no allow_no_pwd can never log in; only TRUE opens the account, and only an admin can set it."""
    suffix = uuid4().hex[:12]
    locked = {"email": f"locked-{suffix}@e2e.local", "user_name": f"locked-{suffix}"}
    opened = {"email": f"opened-{suffix}@e2e.local", "user_name": f"opened-{suffix}", "allow_no_pwd": True}
    created = []
    try:
        for body in (locked, opened):
            response = api("POST", "/api/v1/admin/users", admin_token, json=body)
            assert response.status_code == 201, response.text[:200]
            created.append(body["email"])

        def login_as(user_name, password=""):
            return requests.post(
                f"{BASE}/api/v1/login/password", json={"user_name": user_name, "password": password}, timeout=15
            )

        assert login_as(locked["user_name"]).status_code == 401
        assert login_as(opened["user_name"]).status_code == 200

        # The generic user update never touches it; the dedicated admin endpoint does.
        response = api("PUT", f"/api/v1/admin/users/{locked['email']}", admin_token, json={"allow_no_pwd": True})
        assert response.status_code == 422, response.text[:200]
        assert login_as(locked["user_name"]).status_code == 401

        path = f"/api/v1/admin/users/{locked['email']}/allow-no-pwd"
        response = api("PUT", path, admin_token, json={"allow_no_pwd": True})
        assert response.status_code == 200, response.text[:200]
        assert response.json()["allow_no_pwd"] is True
        assert login_as(locked["user_name"]).status_code == 200
        response = api("PUT", path, admin_token, json={"allow_no_pwd": False})
        assert response.status_code == 200, response.text[:200]
        assert login_as(locked["user_name"]).status_code == 401

        # An over-long password is a 422 that names the 72-byte limit, not a 500.
        response = login_as(opened["user_name"], "x" * 73)
        assert response.status_code == 422, response.text[:200]
        assert "72 bytes" in response.text
    finally:
        for email in created:
            api("DELETE", f"/api/v1/admin/users/{email}", admin_token)
