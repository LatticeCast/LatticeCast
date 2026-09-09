# src/util/pg_errors.py
"""Translate deliberate PostgreSQL rejections into HTTP responses.

The row mutation functions and the row_data trigger (V44-V49) refuse bad
input with an explicit SQLSTATE instead of storing it: an unparseable
timestamp, a blob cell reached through an ordinary patch, a write without
workspace permission. Untranslated those surface as 500, which tells the
caller the server broke when the server in fact did its job and the request
was at fault.

Only codes the migrations raise on purpose are mapped. Anything else keeps
its 500, because an unrecognised database error genuinely is a server fault.
"""

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError

# SQLSTATE -> HTTP status. See the RAISE ... USING ERRCODE sites in
# migration/V44, V45, V47, V48, V49.
_SQLSTATE_STATUS: dict[str, int] = {
    "22023": status.HTTP_422_UNPROCESSABLE_ENTITY,  # invalid_parameter_value
    "23514": status.HTTP_422_UNPROCESSABLE_ENTITY,  # check_violation
    "42501": status.HTTP_403_FORBIDDEN,  # insufficient_privilege
}


def sqlstate_of(exc: BaseException) -> str | None:
    """Dig the SQLSTATE out of a wrapped asyncpg error.

    The asyncpg dialect wraps twice: SQLAlchemy's DBAPIError.orig is an
    AsyncAdapt_asyncpg_dbapi.Error whose __cause__ is the asyncpg exception
    that actually carries `sqlstate`.
    """
    seen: set[int] = set()
    candidate: BaseException | None = exc
    while candidate is not None and id(candidate) not in seen:
        seen.add(id(candidate))
        code = getattr(candidate, "sqlstate", None)
        if isinstance(code, str) and code:
            return code
        candidate = getattr(candidate, "orig", None) or getattr(candidate, "__cause__", None)
    return None


def pg_message_of(exc: BaseException) -> str:
    """The plpgsql RAISE message, without the driver's class-name prefix."""
    text = str(exc)
    _, _, tail = text.rpartition(">: ")
    return (tail or text).strip()


def http_error_for(exc: DBAPIError) -> HTTPException | None:
    """Map a database error to an HTTPException, or None to let it stay a 500."""
    code = sqlstate_of(exc)
    if code is None:
        return None
    mapped = _SQLSTATE_STATUS.get(code)
    if mapped is None:
        return None
    return HTTPException(status_code=mapped, detail=pg_message_of(exc))
