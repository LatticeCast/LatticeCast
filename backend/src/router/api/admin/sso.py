# router/api/admin/sso.py
"""SSO client registration (mounted at /api/v1/admin/sso; admin guard is on the parent)."""

import secrets
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_login_session
from util.security import ensure_bcrypt_length, hash_password_async

router = APIRouter(prefix="/sso", tags=["admin-sso"])


class ClientCreateRequest(BaseModel):
    client_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    display_name: str = Field(min_length=1, max_length=200)
    client_kind: Literal["public", "confidential"]
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    client_secret: str | None = Field(default=None, min_length=16, max_length=512)

    _client_secret_fits_bcrypt = field_validator("client_secret")(ensure_bcrypt_length)


class ClientCreateResponse(BaseModel):
    client_id: str
    client_kind: Literal["public", "confidential"]
    redirect_uris: list[str]
    client_secret: str | None = None


def _valid_redirect_uri(uri: str) -> bool:
    parsed = urlsplit(uri)
    # The App uses /handoff and opens a first-party web callback. Restricting
    # registrations to HTTPS avoids arbitrary custom-scheme redirect capture.
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.fragment


@router.post("/clients", response_model=ClientCreateResponse, status_code=201)
async def create_client(
    request: ClientCreateRequest,
    session: AsyncSession = Depends(get_login_session),
) -> ClientCreateResponse:
    """Register a first-party client. Return a generated secret exactly once."""
    if len(set(request.redirect_uris)) != len(request.redirect_uris) or not all(
        _valid_redirect_uri(uri) for uri in request.redirect_uris
    ):
        raise HTTPException(status_code=422, detail="redirect_uris must be distinct absolute URIs without fragments")
    if request.client_kind == "public" and request.client_secret:
        raise HTTPException(status_code=422, detail="public clients cannot have a client_secret")
    secret = request.client_secret or (secrets.token_urlsafe(36) if request.client_kind == "confidential" else None)
    try:
        await session.execute(
            text(
                "INSERT INTO private.sso_clients "
                "(client_id, client_kind, client_secret_hash, display_name) "
                "VALUES (:client_id, :client_kind, :secret_hash, :display_name)"
            ),
            {
                "client_id": request.client_id,
                "client_kind": request.client_kind,
                "secret_hash": await hash_password_async(secret) if secret else None,
                "display_name": request.display_name,
            },
        )
        for uri in request.redirect_uris:
            await session.execute(
                text(
                    "INSERT INTO private.sso_client_redirect_uris (client_id, redirect_uri, is_default) "
                    "VALUES (:client_id, :redirect_uri, :is_default)"
                ),
                {"client_id": request.client_id, "redirect_uri": uri, "is_default": uri == request.redirect_uris[0]},
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="client_id or redirect_uri already exists") from exc
    return ClientCreateResponse(
        client_id=request.client_id,
        client_kind=request.client_kind,
        redirect_uris=request.redirect_uris,
        client_secret=secret,
    )
