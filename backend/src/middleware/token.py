"""Verify LC-issued access JWTs without contacting external identity providers."""

from fastapi import Header, HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from config.settings import settings
from services.lc_auth import LOCAL_ALGORITHM


def verify_local_token(token: str) -> dict:
    """Verify a locally signed Lattice Cast access JWT."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[LOCAL_ALGORITHM])


async def verify_bearer_token(
    authorization: str | None = Header(None),
) -> dict:
    """Accept only LC-local JWTs; invalid and expired tokens never fall back."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = verify_local_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # Retain the existing API/client representation for LC-local credentials.
    payload["_provider"] = "none"
    return payload
