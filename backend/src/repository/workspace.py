# src/repository/workspace.py
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.workspace import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_name: str) -> Workspace:
        workspace = Workspace(workspace_name=workspace_name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        result = await self.session.execute(select(Workspace).where(Workspace.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID) -> list[Workspace]:
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, Workspace.workspace_id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user_id)
        )
        return list(result.scalars().all())

    async def add_member(self, workspace_id: UUID, user_id: UUID, role: str = "member") -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(self, workspace_id: UUID, user_id: UUID) -> None:
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            await self.session.delete(member)
            await self.session.commit()

    async def get_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        result = await self.session.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def is_member(self, workspace_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def resolve_workspace(self, identifier: str) -> Workspace | None:
        """Resolve a workspace by UUID string or workspace_name (case-insensitive).

        Tries UUID parse first; falls back to LOWER(workspace_name) lookup.
        """
        try:
            workspace_uuid = UUID(identifier)
            workspace = await self.get_by_id(workspace_uuid)
            if workspace:
                return workspace
        except ValueError:
            pass
        # Fallback: case-insensitive workspace_name lookup
        result = await self.session.execute(
            select(Workspace).where(func.lower(Workspace.workspace_name) == identifier.lower())
        )
        return result.scalar_one_or_none()

    async def get_first_owned_workspace(self, user_id: UUID) -> Workspace | None:
        """Return the first workspace the user owns, or any workspace they are a member of."""
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, Workspace.workspace_id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user_id, WorkspaceMember.role == "owner")
            .order_by(Workspace.created_at)
            .limit(1)
        )
        workspace = result.scalar_one_or_none()
        if workspace:
            return workspace
        # Fall back to any membership
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, Workspace.workspace_id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()
