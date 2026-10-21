"""LC-only authentication keeps password login and rejects external credentials."""

from urllib.parse import urlparse
from uuid import uuid4

import pytest
import requests
from playwright.sync_api import expect

from e2e_base import BASE, api


@pytest.mark.parametrize("authorization", [None, "Basic credentials", "Bearer opaque-google-token", "Bearer not.a.jwt"])
def test_invalid_credentials_return_401(authorization):
    headers = {"Authorization": authorization} if authorization is not None else {}
    response = requests.get(f"{BASE}/api/v1/login/me", headers=headers, timeout=10)
    assert response.status_code == 401, response.text
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_retired_oauth_endpoints_are_not_exposed():
    response = requests.get(f"{BASE}/api/v1/openapi.json", timeout=10)
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/login/{provider}/token" not in paths
    for provider in ("authentik", "google"):
        response = requests.post(f"{BASE}/api/v1/login/{provider}/token", json={}, timeout=10)
        assert response.status_code == 404, response.text


def test_password_login_has_no_external_provider_flow(page, admin_token, snapshot):
    user_name = f"local-only-{uuid4().hex[:12]}"
    email = f"{user_name}@e2e.local"
    response = api("POST", "/api/v1/admin/users", admin_token,
                   json={"email": email, "user_name": user_name, "role": "user"})
    assert response.status_code == 201, response.text
    user_id = response.json()["user_id"]
    external_requests = []
    origin = urlparse(BASE).netloc
    page.on("request", lambda request: external_requests.append(request.url)
            if urlparse(request.url).netloc not in ("", origin) else None)
    try:
        page.goto(f"{BASE}/login")
        expect(page.get_by_test_id("login-userid")).to_be_visible()
        expect(page.get_by_test_id("login-authentik")).to_have_count(0)
        expect(page.get_by_test_id("login-google")).to_have_count(0)
        if snapshot:
            page.screenshot(path="/output/local_only_login.png", full_page=True)
        page.get_by_test_id("login-userid").fill(user_name)
        page.get_by_test_id("login-password").fill("local-test-password")
        with page.expect_response("**/api/v1/login/password") as pending:
            page.get_by_test_id("login-start").click()
        login_response = pending.value
        assert login_response.status == 200
        token = login_response.json()["access_token"]
        page.wait_for_url(lambda url: urlparse(url).path != "/login")
        response = api("GET", "/api/v1/login/me", token)
        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == user_id
        assert response.json()["provider"] == "none"
        page.reload()
        expect(page.get_by_test_id("workspace-tab-strip")).to_be_visible()
        assert external_requests == []
        page.goto(f"{BASE}/debug")
        expect(page.get_by_text("LC local", exact=True)).to_be_visible()
        expect(page.get_by_text("Google Client ID:", exact=True)).to_have_count(0)
        if snapshot:
            page.screenshot(path="/output/local_only_debug.png", full_page=True,
                            mask=[page.get_by_text(token, exact=True)])
    finally:
        response = api("DELETE", f"/api/v1/admin/users/{email}", admin_token)
        assert response.status_code == 204, response.text
