# util/security.py

import asyncio

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.bcrypt import BcryptHasher

# bcrypt only reads the first 72 bytes. Rather than silently ignoring the rest, a
# longer secret is rejected: validation turns it into a 422, and verification
# answers False (a wrong password), never a server error.
BCRYPT_MAX_BYTES = 72

_password_hash = PasswordHash((BcryptHasher(),))


class PasswordTooLongError(ValueError):
    pass


def ensure_bcrypt_length(value: str | None) -> str | None:
    """Pydantic validator body: reject secrets bcrypt cannot hash in full."""
    if value is not None and len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(f"must be at most {BCRYPT_MAX_BYTES} bytes (UTF-8)")
    return value


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if len(plain_password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return False
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False


def hash_password(password: str) -> str:
    ensure_bcrypt_length(password)
    return _password_hash.hash(password)


# bcrypt takes tens to hundreds of milliseconds of pure CPU. Called directly in a
# coroutine it blocks the event loop, and with one worker per container that stalls
# every other request. Async routes use these wrappers, which run it in a thread
# (the bcrypt package releases the GIL while hashing).
async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)
