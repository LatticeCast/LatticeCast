"""pwdlib bcrypt: legacy passlib hashes still verify; >72 bytes is rejected, not truncated."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from router.api.auth import PasswordLoginRequest, SetPasswordRequest
from util.security import (
    BCRYPT_MAX_BYTES,
    PasswordTooLongError,
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)

# Produced by passlib 1.7.4 (bcrypt, 12 rounds) before the switch to pwdlib.
LEGACY_HASH = "$2b$12$UJgrrylqPptvMen1fmriuOwDTWGRE5s87lHze4YQvlVx7GFvHjjKa"
LEGACY_PASSWORD = "correct horse battery"


def test_hash_stored_by_passlib_still_verifies():
    assert verify_password(LEGACY_PASSWORD, LEGACY_HASH) is True
    assert verify_password("wrong", LEGACY_HASH) is False


def test_new_hashes_are_bcrypt_2b_with_twelve_rounds():
    assert hash_password("s3cret").startswith("$2b$12$")


def test_password_over_72_bytes_is_rejected_not_truncated():
    too_long = "x" * (BCRYPT_MAX_BYTES + 1)
    with pytest.raises(PasswordTooLongError):
        hash_password(too_long)
    # Multi-byte characters count as bytes: 25 x 3 bytes = 75.
    with pytest.raises(PasswordTooLongError):
        hash_password("字" * 25)
    # Verifying never errors and never matches a truncated prefix.
    assert verify_password(too_long, hash_password("x" * BCRYPT_MAX_BYTES)) is False
    assert hash_password("x" * BCRYPT_MAX_BYTES)


def test_garbage_hash_is_a_failed_verification_not_an_error():
    assert verify_password("anything", "not-a-hash") is False


def test_set_password_request_returns_validation_error_for_long_password():
    SetPasswordRequest(new_password="x" * BCRYPT_MAX_BYTES)
    with pytest.raises(ValidationError):
        SetPasswordRequest(new_password="x" * (BCRYPT_MAX_BYTES + 1))


def test_the_422_names_the_field_and_the_72_byte_limit():
    for model, field, kwargs in (
        (SetPasswordRequest, "new_password", {}),
        (PasswordLoginRequest, "password", {"user_name": "u"}),
    ):
        with pytest.raises(ValidationError) as excinfo:
            model(**{field: "x" * (BCRYPT_MAX_BYTES + 1)}, **kwargs)
        (error,) = excinfo.value.errors()
        assert error["loc"] == (field,)
        assert "at most 72 bytes" in error["msg"]


@pytest.mark.asyncio
async def test_async_wrappers_round_trip():
    hashed = await hash_password_async("pw")
    assert await verify_password_async("pw", hashed) is True
    assert await verify_password_async("nope", hashed) is False
