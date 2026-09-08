# src/repository/workspace.py
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import reapply_rls_context
from models.workspace import Workspace, WorkspaceMember

_LEVEL_ORDER = ("read", "write", "owner")


def _highest_level(actions: list[str]) -> str:
    """Reduce a member's action rows to a single displayed level."""
    for level in reversed(_LEVEL_ORDER):
        if level in actions:
            return level
    return "read"


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_name: str) -> Workspace:
        workspace = Workspace(workspace_name=workspace_name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)  # refreshes attached instance — safe
        return workspace

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        await reapply_rls_context(self.session)
        result = await self.session.execute(select(Workspace).where(Workspace.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID) -> list[Workspace]:
        """Workspaces the user can read.

        No predicate of its own: the workspaces_read policy (V52) already
        returns exactly the rows the caller may read.
        """
        await reapply_rls_context(self.session)
        result = await self.session.execute(select(Workspace))
        return list(result.scalars().all())

    async def grant(self, workspace_id: UUID, user_id: UUID, level: str) -> None:
        """Atomic multi-row grant/revoke — see migration V33's
        grant_workspace_action. Deliberately routed through that
        SECURITY-INVOKER PG function rather than raw INSERT/DELETE here:
        its statements run under the caller's own RLS context, so only
        an existing owner of workspace_id can make this succeed.
        """
        await self.session.execute(
            text("SELECT grant_workspace_action(CAST(:ws AS uuid), CAST(:user_id AS uuid), :level)").bindparams(
                ws=str(workspace_id), user_id=str(user_id), level=level
            )
        )
        await self.session.commit()

    async def remove_member(self, workspace_id: UUID, user_id: UUID) -> None:
        """Delete every action row this member holds (read/write/owner)."""
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        members = result.scalars().all()
        for member in members:
            await self.session.delete(member)
        if members:
            await self.session.commit()

    async def get_members_with_info(self, workspace_id: UUID) -> list["MemberFullResponse"]:
        """One entry per distinct member, aggregated to their highest level."""
        from models.user import UserInfo
        from models.workspace import MemberFullResponse

        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(
                WorkspaceMember.workspace_id,
                WorkspaceMember.user_id,
                UserInfo.user_name,
                UserInfo.email,
                func.array_agg(WorkspaceMember.action).label("actions"),
            )
            .outerjoin(UserInfo, WorkspaceMember.user_id == UserInfo.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .group_by(WorkspaceMember.workspace_id, WorkspaceMember.user_id, UserInfo.user_name, UserInfo.email)
        )
        return [
            MemberFullResponse(
                workspace_id=row.workspace_id,
                user_id=row.user_id,
                user_name=row.user_name,
                email=row.email,
                level=_highest_level(row.actions),
            )
            for row in result.all()
        ]

    async def get_member_with_info(self, workspace_id: UUID, user_id: UUID) -> "MemberFullResponse | None":
        for member in await self.get_members_with_info(workspace_id):
            if member.user_id == user_id:
                return member
        return None

    async def _has_action(self, workspace_id: UUID, user_id: UUID, action: str) -> bool:
        """Does this member hold the given action row on this workspace.

        A plain workspace_members query: workspace_members_self_read (V52)
        exposes the caller's own rows, and workspace_members_owner exposes
        the full roster to an owner of that workspace. Every caller of the
        four public checks below satisfies one of the two.
        """
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(WorkspaceMember.action).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.action == action,
            )
        )
        return result.first() is not None

    async def is_member(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Does this user hold at least 'read' on this workspace."""
        return await self._has_action(workspace_id, user_id, "read")

    async def is_owner(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Does this user hold 'owner' on this workspace."""
        return await self._has_action(workspace_id, user_id, "owner")

    async def can_write(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Does this user hold 'write' on this workspace."""
        return await self._has_action(workspace_id, user_id, "write")

    async def get_user_level(self, workspace_id: UUID, user_id: UUID) -> str:
        """This member's action rows reduced to a single displayed level.

        One aggregate query; a user with no rows reads as "read", the same
        default the three-branch permission CASE used to fall back to.
        """
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(func.array_agg(WorkspaceMember.action)).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return _highest_level(result.scalar_one() or [])

    async def count_owners(self, workspace_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.action == "owner",
            )
        )
        return result.scalar_one()

    async def resolve_workspace(self, identifier: str) -> Workspace | None:
        """Resolve a workspace by UUID string or workspace_name (case-insensitive).

        Tries UUID parse first; falls back to LOWER(workspace_name) lookup.
        """
        await reapply_rls_context(self.session)
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
        """Return the first workspace the user owns, or any workspace they can
        read.

        The owner half joins workspace_members for the caller's own 'owner'
        rows — permitted by workspace_members_self_read (V52). The read
        fallback needs no predicate: workspaces_read has already filtered the
        rows to what the caller may read.
        """
        await reapply_rls_context(self.session)
        result = await self.session.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.workspace_id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.action == "owner",
            )
            .order_by(Workspace.created_at)
            .limit(1)
        )
        workspace = result.scalar_one_or_none()
        if workspace:
            return workspace
        # Fall back to any readable workspace
        result = await self.session.execute(select(Workspace).order_by(Workspace.created_at).limit(1))
        return result.scalar_one_or_none()
