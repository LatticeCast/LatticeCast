"""LC JWT authentication rejects bad credentials without any provider I/O."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jose import jwt

from config.settings import AppSettings, settings
from middleware.token import verify_bearer_token
from services.lc_auth import LOCAL_ALGORITHM, create_lc_access_token


def verify(authorization):
    with patch(
        "httpx.AsyncClient", side_effect=AssertionError("Authentication must not contact providers")
    ) as outbound:
        try:
            return asyncio.run(verify_bearer_token(authorization))
        finally:
            outbound.assert_not_called()


def signed_token(*, expired=False, secret=None, algorithm=LOCAL_ALGORITHM, **claims):
    payload = {
        "sub": "test-user",
        "user_id": "test-user",
        "exp": datetime.now(UTC) + timedelta(minutes=-5 if expired else 5),
        **claims,
    }
    return jwt.encode(payload, secret or settings.jwt_secret_key, algorithm=algorithm)


def test_lc_issued_token_is_accepted_without_network():
    token, _ = create_lc_access_token("test-user")
    result = verify(f"Bearer {token}")
    assert result["user_id"] == "test-user"
    assert result["_provider"] == "none"


@pytest.mark.parametrize("authorization", [None, "", "Basic credentials", "Bearer ", "Bearer opaque-token"])
def test_missing_or_malformed_credentials_return_401(authorization):
    with pytest.raises(HTTPException) as exc:
        verify(authorization)
    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_expired_local_token_returns_401_without_fallback():
    with pytest.raises(HTTPException) as exc:
        verify(f"Bearer {signed_token(expired=True)}")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


@pytest.mark.parametrize("issuer", ["https://authentik.invalid/", "https://accounts.google.com"])
@pytest.mark.parametrize("client_id", ["", "legacy-client"])
def test_foreign_tokens_are_rejected_even_with_legacy_provider_env(issuer, client_id, monkeypatch):
    monkeypatch.setenv("AUTHENTIK_URL", "https://authentik.invalid")
    monkeypatch.setenv("AUTHENTIK_CLIENT_ID", client_id)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "legacy-google-client")
    config = AppSettings()
    assert not hasattr(config, "authentik")
    assert not hasattr(config, "google")
    with pytest.raises(HTTPException) as exc:
        verify(f"Bearer {signed_token(secret='foreign-provider-test-secret', iss=issuer)}")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_other_signing_algorithms_are_not_accepted():
    with pytest.raises(HTTPException) as exc:
        verify(f"Bearer {signed_token(algorithm='HS512')}")
    assert exc.value.status_code == 401


def test_provider_label_cannot_be_overridden_by_token_claims():
    result = verify(f"Bearer {signed_token(_provider='google')}")
    assert result["_provider"] == "none"
