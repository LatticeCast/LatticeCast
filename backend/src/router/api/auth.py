# src/router/api/auth.py
"""
Authentication API endpoints.
"""

from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_login_session, get_session
from middleware.auth import get_current_user, get_rls_session
from middleware.token import create_access_token
from models.user import User
from models.user import UserInfo as UserInfoModel
from models.user import UserPassword
from repository.user import UserRepository, resolve_user_by_email
from util.security import hash_password, verify_password

router = APIRouter(prefix="/login", tags=["auth"])


# --------------------------------------------------
# Pydantic Models
# --------------------------------------------------


class HTTPErrorResponse(BaseModel):
    """Standard error response"""

    detail: str = Field(..., description="Error message")


class TokenRequest(BaseModel):
    """Request body for OAuth token exchange"""

    code: str = Field(..., description="Authorization code from OAuth redirect")
    redirect_uri: str = Field(..., description="Must match the redirect URI used in authorization request")
    code_verifier: str = Field(..., min_length=43, max_length=128, description="PKCE code verifier (43-128 chars)")


class PasswordLoginRequest(BaseModel):
    """Request body for password login (sole FE-visible flow)."""

    user_name: str = Field(..., min_length=1, max_length=64, description="User handle or email")
    password: str = Field(..., description="User password")


class UserInfo(BaseModel):
    """User info from OAuth provider"""

    sub: str = Field(..., description="User ID from provider")
    email: str = Field(
        ..., description="User email or handle (OAuth provides a real address; password login may return the handle)"
    )
    name: str | None = Field(default=None, description="Full name")
    picture: str | None = Field(default=None, description="Profile picture URL")


class TokenResponse(BaseModel):
    """Response from OAuth token exchange"""

    access_token: str = Field(..., description="OAuth access token")
    refresh_token: str | None = Field(default=None, description="OAuth refresh token")
    id_token: str | None = Field(default=None, description="OpenID Connect ID token")
    expires_in: int | None = Field(default=None, description="Token expiration in seconds")
    userinfo: UserInfo = Field(..., description="User profile information")


class MeResponse(BaseModel):
    """Current user information response"""

    user_id: UUID = Field(..., description="User UUID in this system")
    sub: str | None = Field(default=None, description="Subject identifier from OAuth provider")
    email: str = Field(..., description="User email address")
    name: str | None = Field(default=None, description="Display name")
    picture: str | None = Field(default=None, description="Profile picture URL")
    provider: Literal["google", "authentik", "none"] = Field(..., description="OAuth provider used")
    role: str | None = Field(default=None, description="User role in the system")
    user_name: str | None = Field(default=None, description="URL-safe user name")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-user UI config blob (darkMode, lastView per table, …)",
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
    login_session: AsyncSession = Depends(get_login_session),
) -> TokenResponse:
    """Username+password login. Resolves the user by user_name or email and
    returns a self-signed JWT (see `middleware.token.create_access_token`)
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

    email = info.email if info else ident
    name = info.user_name if info else ident

    access_token, expires_in = create_access_token(str(user.user_id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=None,
        id_token=None,
        expires_in=expires_in,
        userinfo=UserInfo(
            sub=str(user.user_id),
            email=email,
            name=name,
            picture=None,
        ),
    )


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
    provider = token_payload.get("_provider", "authentik")

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
    login_session: AsyncSession = Depends(get_login_session),
) -> MeResponse:
    """Update the current user's email. Enforces uniqueness (UNIQUE on gdpr.user_info.email)."""
    existing = await UserRepository(login_session).get_by_email(request.email)
    if existing and existing.user_id != user.user_id:
        raise HTTPException(status_code=409, detail="email already registered")

    info_result = await login_session.execute(
        select(UserInfoModel).where(UserInfoModel.user_id == user.user_id)
    )
    info = info_result.scalar_one_or_none()
    if not info:
        raise HTTPException(status_code=403, detail="User profile not found")
    info.email = request.email
    login_session.add(info)
    await login_session.commit()
    await login_session.refresh(info)

    token_payload = getattr(user, "_token_payload", {})
    provider = token_payload.get("_provider", "authentik")

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
    login_session: AsyncSession = Depends(get_login_session),
) -> dict[str, Any]:
    """Set or change the caller's password_login password (gdpr.user_password).

    First time (no row yet): `current_password` is not required. Once a
    row exists, changing it requires the correct `current_password`.
    Setting a password moves the account off the "no password → JWT
    issued directly" path in `password_login`.
    """
    pwd_result = await login_session.execute(select(UserPassword).where(UserPassword.user_id == user.user_id))
    stored_pwd = pwd_result.scalar_one_or_none()

    if stored_pwd:
        if not request.current_password or not verify_password(request.current_password, stored_pwd.password_hash):
            raise HTTPException(status_code=401, detail="Wrong current_password")
        stored_pwd.password_hash = hash_password(request.new_password)
        login_session.add(stored_pwd)
    else:
        login_session.add(UserPassword(user_id=user.user_id, password_hash=hash_password(request.new_password)))

    await login_session.commit()
    return {"detail": "password updated"}


@router.post(
    "/{provider}/token",
    response_model=TokenResponse,
    responses={
        400: {"model": HTTPErrorResponse, "description": "Invalid authorization code"},
        500: {"model": HTTPErrorResponse, "description": "OAuth not configured"},
        504: {"model": HTTPErrorResponse, "description": "OAuth timeout"},
    },
)
async def token_exchange(
    request: TokenRequest,
    provider: Literal["google", "authentik"] = Path(..., description="OAuth provider"),
) -> TokenResponse:
    """
    Exchange authorization code for tokens.
    Supports Google and Authentik OAuth providers.
    """
    if provider == "google":
        return await _exchange_google(request)
    else:
        return await _exchange_authentik(request)


async def _exchange_google(request: TokenRequest) -> TokenResponse:
    """Exchange Google authorization code for tokens."""
    if not settings.google.client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Exchange code for tokens
            resp = await client.post(
                settings.google.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": request.code,
                    "redirect_uri": request.redirect_uri,
                    "client_id": settings.google.client_id,
                    "client_secret": settings.google.client_secret,
                    "code_verifier": request.code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code != 200:
                detail = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
                raise HTTPException(status_code=400, detail=f"Google token exchange failed: {detail}")

            tokens = resp.json()

            # Fetch user info
            userinfo_resp = await client.get(
                settings.google.userinfo_url,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )

            if userinfo_resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch Google user info")

            userinfo = userinfo_resp.json()

            return TokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                id_token=tokens.get("id_token"),
                expires_in=tokens.get("expires_in"),
                userinfo=UserInfo(
                    sub=userinfo["sub"],
                    email=userinfo["email"],
                    name=userinfo.get("name"),
                    picture=userinfo.get("picture"),
                ),
            )

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Google OAuth timeout") from None
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


async def _exchange_authentik(request: TokenRequest) -> TokenResponse:
    """Exchange Authentik authorization code for tokens (public client)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Exchange code for tokens (public client - no secret needed)
            resp = await client.post(
                settings.authentik.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": request.code,
                    "redirect_uri": request.redirect_uri,
                    "client_id": settings.authentik.client_id,
                    "code_verifier": request.code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code != 200:
                detail = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
                raise HTTPException(status_code=400, detail=f"Authentik token exchange failed: {detail}")

            tokens = resp.json()

            # Fetch user info
            userinfo_resp = await client.get(
                settings.authentik.userinfo_url,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )

            if userinfo_resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch Authentik user info")

            userinfo = userinfo_resp.json()

            return TokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                id_token=tokens.get("id_token"),
                expires_in=tokens.get("expires_in"),
                userinfo=UserInfo(
                    sub=userinfo["sub"],
                    email=userinfo["email"],
                    name=userinfo.get("preferred_username") or userinfo.get("name"),
                    picture=userinfo.get("picture"),
                ),
            )

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Authentik OAuth timeout") from None
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
