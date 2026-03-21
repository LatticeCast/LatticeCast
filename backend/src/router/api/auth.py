# src/router/api/auth.py
"""
Authentication API endpoints.
"""

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, EmailStr, Field

from config.settings import settings
from middleware.auth import get_current_user
from models.user import User

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


class UserInfo(BaseModel):
    """User info from OAuth provider"""

    sub: str = Field(..., description="User ID from provider")
    email: EmailStr = Field(..., description="User email address")
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

    sub: str | None = Field(default=None, description="Subject identifier from OAuth provider")
    email: EmailStr = Field(..., description="User email address")
    name: str | None = Field(default=None, description="Display name")
    picture: str | None = Field(default=None, description="Profile picture URL")
    provider: Literal["google", "authentik", "none"] = Field(..., description="OAuth provider used")
    role: str | None = Field(default=None, description="User role in the system")


# --------------------------------------------------
# Endpoints
# --------------------------------------------------


@router.get(
    "/me",
    response_model=MeResponse,
    responses={
        401: {"model": HTTPErrorResponse, "description": "Invalid or missing token"},
        403: {"model": HTTPErrorResponse, "description": "User not registered"},
    },
)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    """
    Get current user information.
    Requires valid Bearer token and user must be registered in database.
    """
    token_payload = getattr(user, "_token_payload", {})
    provider = token_payload.get("_provider", "authentik")

    return MeResponse(
        sub=token_payload.get("sub"),
        email=user.user_id,
        name=token_payload.get("preferred_username") or token_payload.get("name"),
        picture=token_payload.get("picture"),
        provider=provider,
        role=user.role,
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
