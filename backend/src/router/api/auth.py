# src/router/api/auth.py
"""
Authentication API endpoints.
"""

from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_session
from middleware.auth import get_current_user
from models.user import Gdpr, User
from models.user import UserInfo as UserInfoModel
from repository.user import UserRepository, resolve_user_by_email

router = APIRouter(prefix="/login", tags=["auth"])


# --------------------------------------------------
# Public config endpoint (no auth required)
# --------------------------------------------------


class AppConfigResponse(BaseModel):
    """Public app configuration"""

    auth_required: bool = Field(..., description="Whether OAuth login is required")


@router.get("/config", response_model=AppConfigResponse)
async def get_config() -> AppConfigResponse:
    """Get public app configuration (no auth required)."""
    return AppConfigResponse(auth_required=settings.auth_required)


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
    password: str = Field(..., description="User password (ignored in AUTH_REQUIRED=false mode)")


class UserInfo(BaseModel):
    """User info from OAuth provider"""

    sub: str = Field(..., description="User ID from provider")
    email: str = Field(..., description="User email or handle (OAuth provides a real address; password login may return the handle)")
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


# --------------------------------------------------
# Endpoints
# --------------------------------------------------


@router.post(
    "/password",
    response_model=TokenResponse,
    responses={
        404: {"model": HTTPErrorResponse, "description": "User not registered"},
        501: {"model": HTTPErrorResponse, "description": "Password login disabled — use OAuth"},
    },
)
async def password_login(
    request: PasswordLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Username+password login. In AUTH_REQUIRED=false mode, the password is
    ignored and the resolved user_id UUID is returned as the access token.
    In AUTH_REQUIRED=true mode, returns 501 — clients must use OAuth.
    """
    if settings.auth_required:
        raise HTTPException(
            status_code=501,
            detail="Password login disabled in AUTH_REQUIRED=true mode — use OAuth",
        )

    ident = request.user_name.strip()
    user = await UserRepository(session).resolve_user(ident)
    if not user:
        user = await resolve_user_by_email(ident, session)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered")

    info_result = await session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = info_result.scalar_one_or_none()
    gdpr_result = await session.execute(select(Gdpr).where(Gdpr.user_id == user.user_id))
    gdpr = gdpr_result.scalar_one_or_none()

    email = gdpr.email if gdpr else ident
    name = (gdpr.legal_name if gdpr and gdpr.legal_name else None) or (info.user_name if info else ident)

    return TokenResponse(
        access_token=str(user.user_id),
        refresh_token=None,
        id_token=None,
        expires_in=None,
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
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    """
    Get current user information.
    Requires valid Bearer token and user must be registered in database.

    - email + legal_name come from auth.gdpr (app session, SELECT granted in V32)
    - user_name comes from public.user_info (app session)
    """
    token_payload = getattr(user, "_token_payload", {})
    provider = token_payload.get("_provider", "authentik")

    # public handle/display from app session
    result = await session.execute(select(UserInfoModel).where(UserInfoModel.user_id == user.user_id))
    info = result.scalar_one_or_none()

    # PII from app session (app has SELECT on auth.gdpr after V32)
    gdpr_result = await session.execute(select(Gdpr).where(Gdpr.user_id == user.user_id))
    gdpr = gdpr_result.scalar_one_or_none()

    return MeResponse(
        user_id=user.user_id,
        sub=token_payload.get("sub"),
        email=gdpr.email if gdpr else token_payload.get("email", ""),
        name=(gdpr.legal_name if gdpr and gdpr.legal_name else None)
        or token_payload.get("name", ""),
        picture=token_payload.get("picture"),
        provider=provider,
        role=user.role,
        user_name=info.user_name if info else None,
    )


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
