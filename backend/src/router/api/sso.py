"""Lattice Cast's first-party OAuth-style SSO issuer.

Only registered first-party clients may use these endpoints.  Browser flows
use authorization-code + PKCE; native App handoffs use a confidential client
and are exchanged by that site's backend, never by its frontend.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.db import get_login_session
from middleware.auth import get_current_user, require_admin
from middleware.token import create_access_token
from models.user import User
from util.security import hash_password, verify_password

router = APIRouter(prefix="/sso", tags=["sso"])

COOKIE_NAME = "lc_sso_session"
SESSION_TTL = timedelta(days=30)
CODE_TTL = timedelta(seconds=60)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    """UTC, represented as the project's TIMESTAMP WITHOUT TIME ZONE contract."""
    return datetime.now(UTC).replace(tzinfo=None)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _redirect_with_code(uri: str, code: str, state: str | None) -> str:
    parts = urlsplit(uri)
    query = list(parse_qsl(parts.query, keep_blank_values=True))
    query.append(("code", code))
    if state is not None:
        query.append(("state", state))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _redirect_with_handoff(uri: str, ticket: str) -> str:
    parts = urlsplit(uri)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, f"handoff={ticket}"))


def _origin(uri: str) -> str:
    parts = urlsplit(uri)
    return f"{parts.scheme}://{parts.netloc}"


async def create_browser_session(session: AsyncSession, user_id: UUID, auth_method: str) -> tuple[str, int]:
    """Create an opaque central-session cookie; only its SHA-256 hash reaches PG."""
    raw_token = secrets.token_urlsafe(48)
    expires_at = _now() + SESSION_TTL
    await session.execute(
        text(
            "INSERT INTO private.sso_sessions "
            "(session_token_hash, user_id, auth_method, expires_at) "
            "VALUES (:token_hash, :user_id, :auth_method, :expires_at)"
        ),
        {
            "token_hash": _hash(raw_token),
            "user_id": user_id,
            "auth_method": auth_method,
            "expires_at": expires_at,
        },
    )
    await session.commit()
    return raw_token, int(SESSION_TTL.total_seconds())


def set_browser_session_cookie(response: Response, raw_token: str, max_age: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.sso_cookie_secure,
        samesite="lax",
        path="/",
    )


async def _registered_client(session: AsyncSession, client_id: str, redirect_uri: str) -> dict:
    result = await session.execute(
        text(
            "SELECT c.client_id, c.client_kind, c.client_secret_hash "
            "FROM private.sso_clients c "
            "JOIN private.sso_client_redirect_uris r USING (client_id) "
            "WHERE c.client_id = :client_id AND r.redirect_uri = :redirect_uri "
            "AND c.is_active"
        ),
        {"client_id": client_id, "redirect_uri": redirect_uri},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=400, detail="Unknown client_id or redirect_uri")
    return dict(row)


async def _default_client(session: AsyncSession, client_id: str) -> dict:
    result = await session.execute(
        text(
            "SELECT c.client_id, c.client_kind, c.client_secret_hash, r.redirect_uri "
            "FROM private.sso_clients c "
            "JOIN private.sso_client_redirect_uris r USING (client_id) "
            "WHERE c.client_id = :client_id AND c.is_active AND r.is_default"
        ),
        {"client_id": client_id},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=400, detail="Unknown client_id or no default redirect_uri")
    return dict(row)


async def _issue_code(
    session: AsyncSession,
    *,
    user_id: UUID,
    client_id: str,
    redirect_uri: str,
    session_token: str | None,
    code_challenge: str | None,
    flow_type: str = "authorization_code",
) -> str:
    raw_code = secrets.token_urlsafe(32)
    session_id = None
    if session_token:
        row = await session.execute(
            text("SELECT session_id FROM private.sso_sessions WHERE session_token_hash = :token_hash"),
            {"token_hash": _hash(session_token)},
        )
        session_id = row.scalar_one_or_none()
    await session.execute(
        text(
            "INSERT INTO private.sso_authorization_codes "
            "(code_hash, client_id, user_id, session_id, redirect_uri, code_challenge, code_challenge_method, flow_type, expires_at) "
            "VALUES (:code_hash, :client_id, :user_id, :session_id, :redirect_uri, :code_challenge, :method, :flow_type, :expires_at)"
        ),
        {
            "code_hash": _hash(raw_code),
            "client_id": client_id,
            "user_id": user_id,
            "session_id": session_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "method": "S256" if code_challenge else None,
            "flow_type": flow_type,
            "expires_at": _now() + CODE_TTL,
        },
    )
    await session.commit()
    return raw_code


class TokenRequest(BaseModel):
    code: str = Field(min_length=20, max_length=512)
    client_id: str = Field(min_length=1, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128)
    client_secret: str | None = Field(default=None, min_length=16, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    user_id: UUID


class HandoffRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)


class HandoffResponse(BaseModel):
    launch_url: str
    expires_in: int


class BrowserTokenRequest(BaseModel):
    handoff_ticket: str = Field(min_length=20, max_length=512)
    client_id: str = Field(min_length=1, max_length=128)


class ClientCreateRequest(BaseModel):
    client_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    display_name: str = Field(min_length=1, max_length=200)
    client_kind: Literal["public", "confidential"]
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    client_secret: str | None = Field(default=None, min_length=16, max_length=512)


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
    _: User = Depends(require_admin),
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
                "secret_hash": hash_password(secret) if secret else None,
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


@router.get("/authorize")
async def authorize(
    client_id: str = Query(min_length=1, max_length=128),
    redirect_uri: str = Query(min_length=1, max_length=2048),
    code_challenge: str = Query(min_length=43, max_length=128),
    state: str | None = Query(default=None, max_length=2048),
    sso_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    session: AsyncSession = Depends(get_login_session),
) -> RedirectResponse:
    """Issue a PKCE-bound code using the caller's central browser session."""
    await _registered_client(session, client_id, redirect_uri)
    if not sso_session:
        raise HTTPException(status_code=401, detail="Lattice Cast SSO login required")
    result = await session.execute(
        text(
            "UPDATE private.sso_sessions SET last_seen_at = :now "
            "WHERE session_token_hash = :token_hash AND revoked_at IS NULL AND expires_at > :now "
            "RETURNING user_id"
        ),
        {"token_hash": _hash(sso_session), "now": _now()},
    )
    user_id = result.scalar_one_or_none()
    if not user_id:
        await session.rollback()
        raise HTTPException(status_code=401, detail="Lattice Cast SSO session expired")
    code = await _issue_code(
        session,
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        session_token=sso_session,
        code_challenge=code_challenge,
    )
    return RedirectResponse(_redirect_with_code(redirect_uri, code, state), status_code=303)


@router.post("/handoff", response_model=HandoffResponse)
async def handoff(
    request: HandoffRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_login_session),
) -> HandoffResponse:
    """App bearer token → Lattice Cast launch URL for a public static client."""
    client = await _default_client(session, request.client_id)
    if client["client_kind"] != "public":
        raise HTTPException(status_code=400, detail="Native handoff requires a public client")
    code = await _issue_code(
        session,
        user_id=user.user_id,
        client_id=request.client_id,
        redirect_uri=client["redirect_uri"],
        session_token=None,
        code_challenge=None,
        flow_type="native_launch",
    )
    return HandoffResponse(
        launch_url=f"{settings.sso_issuer_url.rstrip('/')}/api/v1/sso/launch?ticket={code}",
        expires_in=int(CODE_TTL.total_seconds()),
    )


@router.get("/launch", response_class=RedirectResponse, status_code=303)
async def launch(ticket: str = Query(min_length=20, max_length=512), session: AsyncSession = Depends(get_login_session)) -> RedirectResponse:
    """Consume an App launch ticket and redirect with a new fragment-only browser ticket."""
    now = _now()
    result = await session.execute(
        text(
            "UPDATE private.sso_authorization_codes SET consumed_at = :now "
            "WHERE code_hash = :code_hash AND flow_type = 'native_launch' "
            "AND consumed_at IS NULL AND expires_at > :now "
            "RETURNING user_id, client_id, redirect_uri"
        ),
        {"now": now, "code_hash": _hash(ticket)},
    )
    launch_code = result.mappings().one_or_none()
    if not launch_code:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Invalid, expired, or already-used launch ticket")
    browser_ticket = await _issue_code(
        session,
        user_id=launch_code["user_id"],
        client_id=launch_code["client_id"],
        redirect_uri=launch_code["redirect_uri"],
        session_token=None,
        code_challenge=None,
        flow_type="browser_exchange",
    )
    return RedirectResponse(_redirect_with_handoff(launch_code["redirect_uri"], browser_ticket), status_code=303)


@router.post("/browser-token", response_model=TokenResponse)
async def browser_token(
    payload: BrowserTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_login_session),
) -> TokenResponse:
    """Atomically exchange a fragment-only native handoff ticket for a short-lived JWT."""
    client = await _default_client(session, payload.client_id)
    if request.headers.get("origin") != _origin(client["redirect_uri"]):
        raise HTTPException(status_code=403, detail="Origin is not registered for this client")
    now = _now()
    result = await session.execute(
        text(
            "UPDATE private.sso_authorization_codes SET consumed_at = :now "
            "WHERE code_hash = :code_hash AND flow_type = 'browser_exchange' "
            "AND client_id = :client_id AND redirect_uri = :redirect_uri "
            "AND consumed_at IS NULL AND expires_at > :now RETURNING user_id"
        ),
        {"now": now, "code_hash": _hash(payload.handoff_ticket), "client_id": payload.client_id, "redirect_uri": client["redirect_uri"]},
    )
    ticket = result.mappings().one_or_none()
    if not ticket:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Invalid, expired, or already-used browser ticket")
    await session.commit()
    access_token, expires_in = create_access_token(str(ticket["user_id"]), expires_minutes=5)
    return TokenResponse(access_token=access_token, expires_in=expires_in, user_id=ticket["user_id"])


@router.post("/token", response_model=TokenResponse)
async def token(request: TokenRequest, session: AsyncSession = Depends(get_login_session)) -> TokenResponse:
    """Atomically consume one code and issue the existing Lattice Cast JWT format."""
    client = await _registered_client(session, request.client_id, request.redirect_uri)
    if client["client_kind"] == "public":
        if not request.code_verifier:
            raise HTTPException(status_code=400, detail="code_verifier is required for public clients")
    elif not request.client_secret or not verify_password(request.client_secret, client["client_secret_hash"]):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    result = await session.execute(
        text(
            "UPDATE private.sso_authorization_codes SET consumed_at = :now "
            "WHERE code_hash = :code_hash AND client_id = :client_id "
            "AND redirect_uri = :redirect_uri AND consumed_at IS NULL AND expires_at > :now "
            "RETURNING user_id, code_challenge"
        ),
        {
            "now": _now(),
            "code_hash": _hash(request.code),
            "client_id": request.client_id,
            "redirect_uri": request.redirect_uri,
        },
    )
    code = result.mappings().one_or_none()
    if not code:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Invalid, expired, or already-used authorization code")
    if code["code_challenge"] and _pkce_challenge(request.code_verifier or "") != code["code_challenge"]:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Invalid code_verifier")
    if client["client_kind"] == "public" and not code["code_challenge"]:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Public-client code is not PKCE bound")
    await session.commit()
    access_token, expires_in = create_access_token(str(code["user_id"]))
    return TokenResponse(access_token=access_token, expires_in=expires_in, user_id=code["user_id"])


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    sso_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    session: AsyncSession = Depends(get_login_session),
) -> Response:
    if sso_session:
        await session.execute(
            text("UPDATE private.sso_sessions SET revoked_at = :now WHERE session_token_hash = :token_hash"),
            {"now": _now(), "token_hash": _hash(sso_session)},
        )
        await session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
