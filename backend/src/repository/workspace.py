# src/repository/workspace.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.workspace import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_id: str, name: str) -> Workspace:
        workspace = Workspace(workspace_id=workspace_id, name=name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def get_by_id(self, workspace_id: str) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(Workspace.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Workspace]:
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, Workspace.workspace_id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user_id)
        )
        return list(result.scalars().all())

    async def add_member(self, workspace_id: str, user_id: str, role: str = "member") -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(self, workspace_id: str, user_id: str) -> None:
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

    async def get_members(self, workspace_id: str) -> list[WorkspaceMember]:
        result = await self.session.execute(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def is_member(self, workspace_id: str, user_id: str) -> bool:
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None
