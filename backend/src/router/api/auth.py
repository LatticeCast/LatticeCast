# src/router/api/auth.py
"""
Authentication API endpoints.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session
from middleware.auth import get_current_user, get_rls_session
from models.user import User, UserPassword
from models.user import UserInfo as UserInfoModel
from repository.user import UserRepository, resolve_user_by_email
from services.lc_auth import (
    create_browser_session,
    create_lc_access_token,
    hash_refresh_token,
    issue_refresh_token,
    set_browser_session_cookie,
)
from util.security import hash_password, verify_password

router = APIRouter(prefix="/login", tags=["auth"])


# --------------------------------------------------
# Pydantic Models
# --------------------------------------------------


class HTTPErrorResponse(BaseModel):
    """Standard error response"""

    detail: str = Field(..., description="Error message")


class PasswordLoginRequest(BaseModel):
    """Request body for password login (sole FE-visible flow)."""

    user_name: str = Field(..., min_length=1, max_length=64, description="User handle or email")
    password: str = Field(..., description="User password")


class RefreshTokenRequest(BaseModel):
    """Exchange one opaque Lattice Cast refresh token for a new pair."""

    refresh_token: str = Field(..., min_length=32, max_length=512, description="Opaque refresh token")


class RefreshLogoutRequest(BaseModel):
    """Revoke the refresh-token family held by this device."""

    refresh_token: str = Field(..., min_length=32, max_length=512, description="Opaque refresh token")


class UserInfo(BaseModel):
    """LC user information"""

    sub: str = Field(..., description="LC user identifier")
    email: str = Field(..., description="User email or handle")
    name: str | None = Field(default=None, description="Full name")
    picture: str | None = Field(default=None, description="Profile picture URL")


class TokenResponse(BaseModel):
    """Locally issued LC credentials"""

    access_token: str = Field(..., description="LC-local access JWT")
    refresh_token: str | None = Field(default=None, description="Refresh token, when the login flow supports rotation")
    id_token: str | None = Field(default=None, description="OpenID Connect ID token")
    expires_in: int | None = Field(default=None, description="Token expiration in seconds")
    userinfo: UserInfo = Field(..., description="User profile information")


class MeResponse(BaseModel):
    """Current user information response"""

    user_id: UUID = Field(..., description="User UUID in this system")
    sub: str | None = Field(default=None, description="LC subject identifier")
    email: str = Field(..., description="User email address")
    name: str | None = Field(default=None, description="Display name")
    picture: str | None = Field(default=None, description="Profile picture URL")
    provider: Literal["none"] = Field(..., description="LC-local authentication (none means no external provider)")
    role: str | None = Field(default=None, description="User role in the system")
    user_name: str | None = Field(default=None, description="URL-safe user name")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-user UI config blob (darkMode, lastView per table, …)",
    )


def _utc_now() -> datetime:
    """Return a timezone-aware UTC instant for TIMESTAMPTZ persistence."""
    return datetime.now(UTC)


def _token_response(
    user_id: UUID, info: UserInfoModel | None, fallback_email: str, refresh_token: str
) -> TokenResponse:
    access_token, expires_in = create_lc_access_token(str(user_id))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=None,
        expires_in=expires_in,
        userinfo=UserInfo(
            sub=str(user_id),
            email=info.email if info else fallback_email,
            name=info.user_name if info else fallback_email,
            picture=None,
        ),
    )


# --------------------------------------------------
# Endpoints
# --------------------------------------------------


@router.post(
    "/password",
    response_model=TokenResponse,
    responses={
        401: {"model": HTTPErrorResponse, "description": "Wrong password"},
        404: {"model": HTTPErrorResponse, "description": "User not registered"},
    },
)
async def password_login(
    request: PasswordLoginRequest,
    response: Response,
    login_session: AsyncSession = Depends(get_login_session),
) -> TokenResponse:
    """Username+password login. Resolves the user by user_name or email and
    returns a locally signed Lattice Cast access JWT
    as the access token.

    If the account has no row in gdpr.user_password, the supplied
    password is not checked — the JWT is issued directly. If a row
    exists, the password must match the stored bcrypt hash. This
    replaces the old global AUTH_REQUIRED=true/false split with a
    per-account setting (see `PUT /login/me/password`).

    Uses the login_session (mgr_user, BYPASSRLS) because at login time no
    user is authenticated yet — the app_session's RLS filter would return
    zero rows for any lookup.
    """
    ident = request.user_name.strip()
    user = await UserRepository(login_session).resolve_user(ident)
    if not user:
        user = await resolve_user_by_email(ident, login_session)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered")

    info_result = await login_session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = info_result.scalar_one_or_none()

    pwd_result = await login_session.execute(select(UserPassword).where(UserPassword.user_id == user.user_id))
    stored_pwd = pwd_result.scalar_one_or_none()

    if stored_pwd and not verify_password(request.password, stored_pwd.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password")

    sso_token, sso_max_age = await create_browser_session(login_session, user.user_id, "password")
    set_browser_session_cookie(response, sso_token, sso_max_age)
    refresh_token = await issue_refresh_token(login_session, user.user_id)
    return _token_response(user.user_id, info, ident, refresh_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"model": HTTPErrorResponse, "description": "Invalid, expired, or already-used refresh token"}},
)
async def refresh_login(
    request: RefreshTokenRequest,
    login_session: AsyncSession = Depends(get_login_session),
) -> TokenResponse:
    """Atomically rotate an App refresh token.

    A refresh token is single-use. Replaying an already-used token revokes its
    complete family, which also invalidates the latest token issued to a stolen
    device. The client must then perform password login again.
    """
    now = _utc_now()
    token_hash = hash_refresh_token(request.refresh_token)
    rotated = await login_session.execute(
        text(
            """
            UPDATE private.sso_refresh_tokens
            SET revoked_at = :now, replaced_at = :now
            WHERE token_hash = :token_hash
              AND revoked_at IS NULL
              AND expires_at > :now
            RETURNING user_id, family_id, session_id
            """
        ),
        {"token_hash": token_hash, "now": now},
    )
    token_row = rotated.mappings().one_or_none()
    if not token_row:
        # If this was a replay of an old member of a family, invalidate the
        # family before returning. Unknown/expired values simply affect no row.
        family = await login_session.execute(
            text("SELECT family_id FROM private.sso_refresh_tokens WHERE token_hash = :token_hash"),
            {"token_hash": token_hash},
        )
        family_id = family.scalar_one_or_none()
        if family_id:
            await login_session.execute(
                text(
                    """
                    UPDATE private.sso_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, :now)
                    WHERE family_id = :family_id
                    """
                ),
                {"family_id": family_id, "now": now},
            )
        await login_session.commit()
        raise HTTPException(status_code=401, detail="Invalid, expired, or already-used refresh token")

    refresh_token = await issue_refresh_token(
        login_session,
        token_row["user_id"],
        family_id=token_row["family_id"],
        session_id=token_row["session_id"],
        commit=False,
    )
    info_result = await login_session.execute(
        select(UserInfoModel).where(UserInfoModel.user_id == token_row["user_id"])
    )
    info = info_result.scalar_one_or_none()
    await login_session.commit()
    return _token_response(token_row["user_id"], info, str(token_row["user_id"]), refresh_token)


@router.post("/logout", status_code=204)
async def logout_refresh_token(
    request: RefreshLogoutRequest,
    login_session: AsyncSession = Depends(get_login_session),
) -> Response:
    """Revoke all rotating refresh tokens belonging to the supplied device family."""
    token_hash = hash_refresh_token(request.refresh_token)
    family = await login_session.execute(
        text("SELECT family_id FROM private.sso_refresh_tokens WHERE token_hash = :token_hash"),
        {"token_hash": token_hash},
    )
    family_id = family.scalar_one_or_none()
    if family_id:
        await login_session.execute(
            text(
                """
                UPDATE private.sso_refresh_tokens
                SET revoked_at = COALESCE(revoked_at, :now)
                WHERE family_id = :family_id
                """
            ),
            {"family_id": family_id, "now": _utc_now()},
        )
    await login_session.commit()
    return Response(status_code=204)


@router.get(
    "/me",
    response_model=MeResponse,
    responses={
        401: {"model": HTTPErrorResponse, "description": "Invalid or missing token"},
        403: {"model": HTTPErrorResponse, "description": "User not registered"},
    },
)
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> MeResponse:
    """
    Get current user information.
    Requires valid Bearer token and user must be registered in database.

    v40: email + user_name + config all live in gdpr.user_info. Uses
    get_rls_session so `app.current_user_id` is set and the gdpr RLS
    policy `user_id = current_user_id` matches the caller's row.
    """
    token_payload = getattr(user, "_token_payload", {})
    provider = token_payload.get("_provider", "none")

    result = await session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = result.scalar_one_or_none()

    return MeResponse(
        user_id=user.user_id,
        sub=token_payload.get("sub"),
        email=info.email if info else token_payload.get("email", ""),
        name=token_payload.get("name", "") or (info.user_name if info else ""),
        picture=token_payload.get("picture"),
        provider=provider,
        role=user.role,
        user_name=info.user_name if info else None,
        config=info.config if info and info.config else {},
    )


# --------------------------------------------------
# Per-user config (public.user_info.config)
# --------------------------------------------------


@router.patch(
    "/me/config",
    response_model=dict[str, Any],
    responses={
        401: {"model": HTTPErrorResponse, "description": "Invalid or missing token"},
        403: {"model": HTTPErrorResponse, "description": "User not registered"},
    },
)
async def patch_me_config(
    patch: dict[str, Any],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Shallow-merge the supplied keys into the caller's user_info.config.

    A top-level value of `null` removes that key. Returns the new full
    config blob. Body must be a JSON object; nested values are replaced
    wholesale (no deep merge).
    """
    if not isinstance(patch, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")

    result = await session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = result.scalar_one_or_none()
    if not info:
        raise HTTPException(status_code=403, detail="User profile not found")

    merged = {**(info.config or {})}
    for k, v in patch.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v

    info.config = merged
    session.add(info)
    await session.commit()
    return merged


class UpdateEmailRequest(BaseModel):
    """Request body for updating the current user's email."""

    email: str = Field(..., description="New email address")


@router.put(
    "/me/email",
    response_model=MeResponse,
    responses={
        401: {"model": HTTPErrorResponse, "description": "Invalid or missing token"},
        403: {"model": HTTPErrorResponse, "description": "User not registered"},
        409: {"model": HTTPErrorResponse, "description": "Email already registered"},
    },
)
async def update_me_email(
    request: UpdateEmailRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> MeResponse:
    """Update the current user's email through the self-row RLS policy."""
    existing = await UserRepository(session).get_by_email(request.email)
    if existing and existing.user_id != user.user_id:
        raise HTTPException(status_code=409, detail="email already registered")

    info_result = await session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = info_result.scalar_one_or_none()
    if not info:
        raise HTTPException(status_code=403, detail="User profile not found")
    info.email = request.email
    session.add(info)
    await session.commit()
    await session.refresh(info)

    token_payload = getattr(user, "_token_payload", {})
    provider = token_payload.get("_provider", "none")

    return MeResponse(
        user_id=user.user_id,
        sub=token_payload.get("sub"),
        email=info.email,
        name=token_payload.get("name", "") or info.user_name,
        picture=token_payload.get("picture"),
        provider=provider,
        role=user.role,
        user_name=info.user_name,
        config=info.config or {},
    )


class SetPasswordRequest(BaseModel):
    """Request body for setting/changing the current user's password."""

    new_password: str = Field(..., min_length=1, description="New password")
    current_password: str | None = Field(
        default=None, description="Required only if the account already has a password set"
    )


@router.put(
    "/me/password",
    response_model=dict[str, Any],
    responses={
        401: {"model": HTTPErrorResponse, "description": "Invalid or missing token, or wrong current_password"},
        403: {"model": HTTPErrorResponse, "description": "User not registered"},
    },
)
async def set_me_password(
    request: SetPasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, Any]:
    """Set or change the caller's password_login password (gdpr.user_password).

    First time (no row yet): `current_password` is not required. Once a
    row exists, changing it requires the correct `current_password`.
    Setting a password moves the account off the "no password → JWT
    issued directly" path in `password_login`.
    """
    pwd_result = await session.execute(text("SELECT public.get_current_user_password_hash()"))
    stored_password_hash = pwd_result.scalar_one()

    if stored_password_hash:
        if not request.current_password or not verify_password(request.current_password, stored_password_hash):
            raise HTTPException(status_code=401, detail="Wrong current_password")

    await session.execute(
        text("SELECT public.set_current_user_password_hash(:password_hash)").bindparams(
            password_hash=hash_password(request.new_password)
        )
    )
    await session.commit()
    return {"detail": "password updated"}
