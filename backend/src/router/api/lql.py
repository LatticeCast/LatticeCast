"""Execute caller-provided LQL within one readable workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from config.lattice_ql import compile_lql
from middleware.auth import get_current_user, get_rls_session
from models.user import User
from repository.dashboard import DashboardRepository
from repository.workspace import WorkspaceRepository
from util.pg_errors import sqlstate_of

router = APIRouter(prefix="/workspaces", tags=["lql"])

# datatype_mismatch, undefined_function (no such operator), cannot_coerce
_TYPE_ERROR_SQLSTATES = frozenset({"42804", "42883", "42846"})


class LQLRequest(BaseModel):
    lql: str = Field(min_length=1)


@router.post("/{workspace_id}/lql")
async def query_workspace_lql(
    workspace_id: UUID,
    body: LQLRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
) -> dict[str, list[dict]]:
    """Compile and execute LQL against the caller's readable workspace."""
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        sql, params = await compile_lql(body.lql, str(workspace.workspace_id), session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        rows = await DashboardRepository.execute(session, sql, params)
    except DBAPIError as exc:
        # The caller wrote this query, so a type mismatch is their error, not a server fault.
        code = sqlstate_of(exc)
        if code is not None and (code.startswith("22") or code in _TYPE_ERROR_SQLSTATES):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"LQL query failed with a database type error ({code}); check the compared values against the column types",
            ) from exc
        raise
    return {"rows": rows}
