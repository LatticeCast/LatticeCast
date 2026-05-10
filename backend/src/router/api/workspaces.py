# src/router/api/workspaces.py

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import get_current_user, get_rls_session
from models.user import User
from models.workspace import (
    MemberCreate,
    MemberFullResponse,
    MemberRoleUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceMember,
    WorkspaceResponse,
)
from repository.user import resolve_user_by_email
from repository.workspace import WorkspaceRepository


async def _resolve_member_user(
    data: MemberCreate,
    session: AsyncSession,
) -> User:
    """Resolve user by user_id (UUID), user_name, or user_email using app session.

    app has SELECT on auth.gdpr after V32, so email lookups no longer need login_session.
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


async def _require_owner(workspace_id: UUID, user_id: UUID, session: AsyncSession):
    result = await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.role == "owner",
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


async def _count_owners(workspace_id: UUID, session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner",
        )
    )
    return result.scalar_one()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Create a new workspace; creator becomes owner"""
    if data.workspace_name.lower() in RESERVED_WORKSPACE_NAMES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That workspace name is reserved")
    repo = WorkspaceRepository(session)
    conflict = await session.execute(
        select(Workspace).where(func.lower(Workspace.workspace_name) == data.workspace_name.lower())
    )
    if conflict.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A workspace with that name already exists")
    workspace = await repo.create(workspace_name=data.workspace_name)
    await repo.add_member(workspace_id=workspace.workspace_id, user_id=user.user_id, role="owner")
    return workspace


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List all workspaces the current user is a member of"""
    repo = WorkspaceRepository(session)
    return await repo.list_by_user(user.user_id)


@router.get("/{workspace_id}/members", response_model=list[MemberFullResponse])
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """List all members of a workspace (must be a member). Returns user_name and email joined from auth tables."""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    if not await repo.is_member(workspace.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")
    return await repo.get_members_with_info(workspace.workspace_id)


@router.post("/{workspace_id}/members", response_model=MemberFullResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: str,
    data: MemberCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Add a member to a workspace (owner only)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    new_member = await _resolve_member_user(data, session)
    if await repo.is_member(workspace.workspace_id, new_member.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")
    await repo.add_member(workspace_id=workspace.workspace_id, user_id=new_member.user_id, role=data.role)
    return await repo.get_member_with_info(workspace.workspace_id, new_member.user_id)


@router.put("/{workspace_id}/members/{member_user_id}", response_model=MemberFullResponse)
async def update_member_role(
    workspace_id: str,
    member_user_id: str,
    data: MemberRoleUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Update a member's role (owner only). Blocks demotion of the last owner."""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    member_data = MemberCreate(user_name=member_user_id)
    try:
        member_data.user_id = UUID(member_user_id)
        member_data.user_name = None
    except ValueError:
        pass
    target = await _resolve_member_user(member_data, session)
    if not await repo.is_member(workspace.workspace_id, target.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if data.role != "owner":
        result = await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.workspace_id,
                WorkspaceMember.user_id == target.user_id,
                WorkspaceMember.role == "owner",
            )
        )
        if result.scalar_one_or_none() is not None:
            if await _count_owners(workspace.workspace_id, session) <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the last owner")
    await repo.update_member_role(workspace.workspace_id, target.user_id, data.role)
    return await repo.get_member_with_info(workspace.workspace_id, target.user_id)


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Remove a member from a workspace (owner only). member_user_id can be UUID or user_name."""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    member_data = MemberCreate(user_name=member_user_id)
    try:
        member_data.user_id = UUID(member_user_id)
        member_data.user_name = None
    except ValueError:
        pass
    member = await _resolve_member_user(member_data, session)
    if not await repo.is_member(workspace.workspace_id, member.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    result = await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.workspace_id,
            WorkspaceMember.user_id == member.user_id,
            WorkspaceMember.role == "owner",
        )
    )
    if result.scalar_one_or_none() is not None:
        if await _count_owners(workspace.workspace_id, session) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last owner")
    await repo.remove_member(workspace_id=workspace.workspace_id, user_id=member.user_id)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Get a workspace by ID (must be a member)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    if not await repo.is_member(workspace.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")
    return workspace


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
    await _require_owner(workspace.workspace_id, user.user_id, session)

    # Check uniqueness: workspace_name is globally unique
    conflict = await session.execute(
        select(Workspace).where(
            func.lower(Workspace.workspace_name) == data.workspace_name.lower(),
            Workspace.workspace_id != workspace.workspace_id,
        )
    )
    if conflict.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A workspace with that name already exists")

    workspace.workspace_name = data.workspace_name
    workspace.updated_at = datetime.utcnow()
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)  # refreshes attached instance — safe
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_rls_session),
):
    """Delete a workspace (owner only)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    await session.delete(workspace)
    await session.commit()
