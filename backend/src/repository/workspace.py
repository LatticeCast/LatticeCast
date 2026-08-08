# src/repository/workspace.py
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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
        result = await self.session.execute(select(Workspace).where(Workspace.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID) -> list[Workspace]:
        """Workspaces the user can read.

        Filters via check_workspace_permission (SECURITY DEFINER)
        instead of joining workspace_members directly: that table's RLS
        is owner-only for every command including SELECT (V33), so a
        JOIN against it under the caller's own RLS session would
        silently drop every workspace they can merely read/write but
        don't own.
        """
        result = await self.session.execute(
            select(Workspace).where(
                text("check_workspace_permission(workspaces.workspace_id, CAST(:user_id AS uuid), 'read')").bindparams(
                    user_id=str(user_id)
                )
            )
        )
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

    async def is_member(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Does this user hold at least 'read' on this workspace.

        Routed through check_workspace_permission (SECURITY DEFINER)
        rather than a direct table query: workspace_members RLS is
        owner-only for every command including SELECT (V33), so a plain
        query would incorrectly return nothing for a non-owner checking
        their own membership — RLS only asks "is the caller an owner of
        this workspace", not "is this the caller's own row".
        """
        result = await self.session.execute(
            text("SELECT check_workspace_permission(CAST(:ws AS uuid), CAST(:user_id AS uuid), 'read')").bindparams(
                ws=str(workspace_id), user_id=str(user_id)
            )
        )
        return bool(result.scalar_one())

    async def is_owner(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Same RLS-bypass reasoning as is_member — see its docstring."""
        result = await self.session.execute(
            text("SELECT check_workspace_permission(CAST(:ws AS uuid), CAST(:user_id AS uuid), 'owner')").bindparams(
                ws=str(workspace_id), user_id=str(user_id)
            )
        )
        return bool(result.scalar_one())

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
        read. See list_by_user's docstring for why this filters via
        check_workspace_permission rather than joining workspace_members."""
        result = await self.session.execute(
            select(Workspace)
            .where(
                text("check_workspace_permission(workspaces.workspace_id, CAST(:user_id AS uuid), 'owner')").bindparams(
                    user_id=str(user_id)
                )
            )
            .order_by(Workspace.created_at)
            .limit(1)
        )
        workspace = result.scalar_one_or_none()
        if workspace:
            return workspace
        # Fall back to any readable membership
        result = await self.session.execute(
            select(Workspace)
            .where(
                text("check_workspace_permission(workspaces.workspace_id, CAST(:user_id AS uuid), 'read')").bindparams(
                    user_id=str(user_id)
                )
            )
            .order_by(Workspace.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()
