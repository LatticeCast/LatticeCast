# src/router/api/workspaces.py

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.user import User
from models.workspace import (
    MemberCreate,
    MemberFullResponse,
    MemberLevelUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceResponse,
)
from repository.user import resolve_user_by_email
from repository.workspace import WorkspaceRepository


async def _resolve_member_user(
    data: MemberCreate,
    session: AsyncSession,
) -> User:
    """Resolve user by user_id (UUID), user_name, or user_email using app session.

    v40: email lives on gdpr.user_info; app role has SELECT on it.
    """
    from models.user import UserInfo

    if data.user_id:
        user = await session.get(User, data.user_id)
        if user:
            return user
    elif data.user_name:
        result = await session.execute(
            select(User)
            .join(UserInfo, User.user_id == UserInfo.user_id)
            .where(func.lower(UserInfo.user_name) == data.user_name.lower())
        )
        user = result.scalar_one_or_none()
        if user:
            return user
    elif data.user_email:
        user = await resolve_user_by_email(data.user_email, session)
        if user:
            return user
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="User not found — provide user_id, user_name, or user_email"
    )


RESERVED_WORKSPACE_NAMES = frozenset({"settings", "config", "members", "login", "callback", "debug", "api"})

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


async def _get_workspace_or_404(workspace_id: str, repo: WorkspaceRepository):
    workspace = await repo.resolve_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


async def _require_owner(workspace_id: UUID, user_id: UUID, repo: WorkspaceRepository):
    if not await repo.is_owner(workspace_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


async def _build_workspace_response(
    workspace: Workspace,
    user_id: UUID,
    repo: WorkspaceRepository,
) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        workspace_name=workspace.workspace_name,
        level=await repo.get_user_level(workspace.workspace_id, user_id),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Create a new workspace; creator becomes owner.

    Delegates to the SECURITY DEFINER PG function `create_workspace` (V46).
    It derives the creator from app.current_user_id, then inserts the
    workspace and read+write+owner rows atomically. It must bypass RLS at
    INSERT time because the creator is not yet a member.
    """
    repo = WorkspaceRepository(session)
    if data.workspace_name.lower() in RESERVED_WORKSPACE_NAMES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That workspace name is reserved")
    try:
        result = await session.execute(text("SELECT create_workspace(:name)").bindparams(name=data.workspace_name))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace with that name already exists",
        ) from exc
    created = result.scalar_one()
    return WorkspaceResponse(
        workspace_id=created["workspace_id"],
        workspace_name=created["workspace_name"],
        level="owner",
        created_at=created["created_at"],
        updated_at=created["updated_at"],
    )


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List all workspaces the current user can read"""
    repo = WorkspaceRepository(session)
    workspaces = await repo.list_by_user(user.user_id)
    return [await _build_workspace_response(workspace, user.user_id, repo) for workspace in workspaces]


@router.get("/{workspace_id}/members", response_model=list[MemberFullResponse])
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List all members of a workspace (owner only — see V33: workspace_members
    RLS is owner-gated for every command, including SELECT). Returns each
    member's user_name/email joined from auth tables, aggregated to their
    highest access level.
    """
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)
    return await repo.get_members_with_info(workspace.workspace_id)


@router.post("/{workspace_id}/members", response_model=MemberFullResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: str,
    data: MemberCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Add a member to a workspace at the given access level (owner only).

    The duplicate check reads the roster, not a permission: `_require_owner`
    has established the caller as an owner, so workspace_members_owner (V52)
    exposes every member of this workspace to the query below.
    """
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)
    new_member = await _resolve_member_user(data, session)
    if await repo.get_member_with_info(workspace.workspace_id, new_member.user_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")
    await repo.grant(workspace_id=workspace.workspace_id, user_id=new_member.user_id, level=data.level)
    return await repo.get_member_with_info(workspace.workspace_id, new_member.user_id)


@router.put("/{workspace_id}/members/{member_user_id}", response_model=MemberFullResponse)
async def update_member_role(
    workspace_id: str,
    member_user_id: str,
    data: MemberLevelUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Update a member's access level (owner only). Blocks demoting the last owner.

    One roster read answers both questions about the target — that it is a
    member at all, and whether it currently holds owner. Readable because the
    caller is an owner (workspace_members_owner, V52).
    """
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)
    member_data = MemberCreate(user_name=member_user_id)
    try:
        member_data.user_id = UUID(member_user_id)
        member_data.user_name = None
    except ValueError:
        pass
    target = await _resolve_member_user(member_data, session)
    target_member = await repo.get_member_with_info(workspace.workspace_id, target.user_id)
    if target_member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if data.level != "owner" and target_member.level == "owner":
        if await repo.count_owners(workspace.workspace_id) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the last owner")
    await repo.grant(workspace.workspace_id, target.user_id, data.level)
    return await repo.get_member_with_info(workspace.workspace_id, target.user_id)


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Remove a member from a workspace (owner only). member_user_id can be UUID or user_name.

    One roster read answers both questions about the target — that it is a
    member at all, and whether it currently holds owner. Readable because the
    caller is an owner (workspace_members_owner, V52).
    """
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)
    member_data = MemberCreate(user_name=member_user_id)
    try:
        member_data.user_id = UUID(member_user_id)
        member_data.user_name = None
    except ValueError:
        pass
    member = await _resolve_member_user(member_data, session)
    target_member = await repo.get_member_with_info(workspace.workspace_id, member.user_id)
    if target_member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target_member.level == "owner":
        if await repo.count_owners(workspace.workspace_id) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last owner")
    await repo.remove_member(workspace_id=workspace.workspace_id, user_id=member.user_id)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Get a workspace by ID (must be able to read it).

    No separate membership check here: `workspaces_read` RLS (V33)
    already scopes the underlying SELECT to workspaces the caller holds
    a 'read' grant on, so an unreadable workspace_id resolves to 404
    via `_get_workspace_or_404` rather than a distinct 403.
    """
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    return await _build_workspace_response(workspace, user.user_id, repo)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Update workspace name (owner only). workspace_name must be globally unique."""
    if data.workspace_name.lower() in RESERVED_WORKSPACE_NAMES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That workspace name is reserved")
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)

    # Check uniqueness: workspace_name is globally unique
    conflict = await session.execute(
        select(Workspace).where(
            func.lower(Workspace.workspace_name) == data.workspace_name.lower(),
            Workspace.workspace_id != workspace.workspace_id,
        )
    )
    if conflict.scalars().first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A workspace with that name already exists")

    workspace.workspace_name = data.workspace_name
    workspace.updated_at = datetime.utcnow()
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)  # refreshes attached instance — safe
    return await _build_workspace_response(workspace, user.user_id, repo)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a workspace (owner only)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, repo)
    await session.delete(workspace)
    await session.commit()
