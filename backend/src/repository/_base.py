# src/repository/_base.py
from sqlalchemy import Executable
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import reapply_rls_context


class RLSRepository:
    """Base for repositories whose reads must run under the caller's RLS identity.

    Subclasses call `self._execute(stmt)` instead of
    `self.session.execute(stmt)` for RLS-scoped reads. `_execute` re-applies
    this session's stashed identity first, so a new method gets the
    guarantee by using the helper rather than by remembering a separate
    `reapply_rls_context` call -- see the "RLS IDENTITY HYGIENE" note in
    `core/db.py` for why re-application can be needed at all.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _execute(self, stmt: Executable, params: dict | None = None) -> Result:
        await reapply_rls_context(self.session)
        return await self.session.execute(stmt, params)
