# src/repository/user.py
import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User, UserInfo
from models.workspace import Workspace, WorkspaceMember


def _slugify(text: str) -> str:
    """Convert text to a user_name matching ^[a-z0-9][a-z0-9_-]{2,31}$."""
    slug = re.sub(r"[^a-z0-9_-]", "-", text.lower())
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"^[^a-z0-9]+", "", slug)
    slug = slug[:32].rstrip("-")
    if len(slug) < 3:
        slug = (slug + "---")[:3]
    return slug


class UserRepository:
    """User identity (auth.users) + PII/handle (gdpr.user_info)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_user_name(self, user_name: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .join(UserInfo, User.user_id == UserInfo.user_id)
            .where(func.lower(UserInfo.user_name) == user_name.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .join(UserInfo, User.user_id == UserInfo.user_id)
            .where(func.lower(UserInfo.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_info(self, user_id: UUID) -> UserInfo | None:
        result = await self.session.execute(select(UserInfo).where(UserInfo.user_id == user_id))
        return result.scalar_one_or_none()

    async def resolve_user(self, identifier: str) -> User | None:
        """Resolve a user by UUID or user_name."""
        try:
            user_uuid = UUID(identifier)
            user = await self.get_by_id(user_uuid)
            if user:
                return user
        except ValueError:
            pass
        return await self.get_by_user_name(identifier)


async def resolve_user_by_email(email: str, session: AsyncSession) -> User | None:
    """Look up a User via gdpr.user_info.email."""
    return await UserRepository(session).get_by_email(email)


async def bootstrap_user(
    login_session: AsyncSession,
    app_session: AsyncSession,
    email: str,
    role: str = "user",
    user_name: str | None = None,
) -> User:
    """Create auth.users + gdpr.user_info + default workspace.

    v40: PII + handle + config merged into gdpr.user_info. Everything
    runs on login_session (mgr_user, BYPASSRLS) because the user isn't
    authenticated yet — the app_session's RLS would reject the workspace
    INSERT (no membership row exists at the moment of insert).
    """
    user = User(role=role)
    login_session.add(user)
    await login_session.flush()

    handle = user_name or _slugify(email)
    info = UserInfo(user_id=user.user_id, email=email, user_name=handle)
    login_session.add(info)

    workspace = Workspace(workspace_name=email)
    login_session.add(workspace)
    await login_session.flush()
    member = WorkspaceMember(
        workspace_id=workspace.workspace_id, user_id=user.user_id, role="owner"
    )
    login_session.add(member)
    await login_session.commit()
    await login_session.refresh(user)
    _ = app_session  # kept for API compatibility; not used in bootstrap
    return user


async def upsert_user_info(
    session: AsyncSession,
    user_id: UUID,
    email: str,
    user_name: str | None = None,
) -> UserInfo:
    """Idempotent upsert on gdpr.user_info — used by auth flow when a
    user logs in via SSO and we don't yet know their PII row."""
    handle = user_name or _slugify(email)
    stmt = (
        pg_insert(UserInfo)
        .values(user_id=user_id, email=email, user_name=handle)
        .on_conflict_do_update(
            index_elements=[UserInfo.user_id],
            set_={"email": email},
        )
    )
    await session.execute(stmt)
    await session.commit()
    result = await session.execute(select(UserInfo).where(UserInfo.user_id == user_id))
    return result.scalar_one()
