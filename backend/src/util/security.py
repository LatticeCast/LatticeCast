# util/security.py

import asyncio

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# bcrypt takes tens to hundreds of milliseconds of pure CPU. Called directly in a
# coroutine it blocks the event loop, and with one worker per container that stalls
# every other request. Async routes use these wrappers, which run it in a thread.
async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)
