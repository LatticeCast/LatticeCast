"""Password self-service uses the authenticated RLS identity end to end."""

from __future__ import annotations

import time

from e2e_base import api


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
            json={"email": email, "user_name": user_name},
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
