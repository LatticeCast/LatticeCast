# src/router/api/workspaces.py

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from middleware.auth import get_current_user
from models.user import User
from models.workspace import MemberCreate, MemberResponse, Workspace, WorkspaceCreate, WorkspaceMember, WorkspaceResponse
from repository.workspace import WorkspaceRepository


async def _resolve_member_user(data: MemberCreate, session: AsyncSession) -> User:
    """Resolve user by user_id (UUID), user_name, or user_email"""
    from models.user import UserInfo
    if data.user_id:
        user = await session.get(User, data.user_id)
        if user:
            return user
    elif data.user_name:
        result = await session.execute(
            select(User).join(UserInfo, User.user_id == UserInfo.user_id).where(
                func.lower(UserInfo.user_name) == data.user_name.lower()
            )
        )
        user = result.scalar_one_or_none()
        if user:
            return user
    elif data.user_email:
        result = await session.execute(
            select(User).join(UserInfo, User.user_id == UserInfo.user_id).where(
                func.lower(UserInfo.email) == data.user_email.lower()
            )
        )
        user = result.scalar_one_or_none()
        if user:
            return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found — provide user_id, user_name, or user_email")


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


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new workspace; creator becomes owner"""
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
    session: AsyncSession = Depends(get_session),
):
    """List all workspaces the current user is a member of"""
    repo = WorkspaceRepository(session)
    return await repo.list_by_user(user.user_id)


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all members of a workspace (must be a member)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    if not await repo.is_member(workspace.workspace_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")
    return await repo.get_members(workspace.workspace_id)


@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: str,
    data: MemberCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Add a member to a workspace (owner only)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    new_member = await _resolve_member_user(data, session)
    if await repo.is_member(workspace.workspace_id, new_member.user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")
    return await repo.add_member(workspace_id=workspace.workspace_id, user_id=new_member.user_id, role=data.role)


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove a member from a workspace (owner only). member_user_id can be UUID or display_id."""
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
    await repo.remove_member(workspace_id=workspace.workspace_id, user_id=member.user_id)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
    session: AsyncSession = Depends(get_session),
):
    """Update workspace name (owner only). workspace_name must be globally unique."""
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
    await session.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a workspace (owner only)"""
    repo = WorkspaceRepository(session)
    workspace = await _get_workspace_or_404(workspace_id, repo)
    await _require_owner(workspace.workspace_id, user.user_id, session)
    await session.delete(workspace)
    await session.commit()
