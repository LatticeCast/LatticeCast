# src/repository/user.py
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import Gdpr, User, UserInfo
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
    """Operates on public tables + SELECT on auth.users.

    Uses app_session by default. For writes to auth.users / auth.gdpr, a
    caller must inject a login session — see `bootstrap_user` below.
    """

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

    async def update(self, user: User, role: str | None = None) -> User:
        if role:
            user.role = role
        user.updated_at = datetime.utcnow()
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def resolve_user(self, identifier: str) -> User | None:
        """Resolve a user by UUID or user_name (app-session-safe).

        Email lookups live on auth.gdpr — use `GdprRepository.get_by_email`
        with a login session instead.
        """
        # 1. UUID
        try:
            user_uuid = UUID(identifier)
            user = await self.get_by_id(user_uuid)
            if user:
                return user
        except ValueError:
            pass
        # 2. user_name (case-insensitive)
        return await self.get_by_user_name(identifier)


class GdprRepository:
    """Operates on auth.gdpr — REQUIRES a login session."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> Gdpr | None:
        result = await self.session.execute(select(Gdpr).where(Gdpr.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Gdpr | None:
        result = await self.session.execute(select(Gdpr).where(func.lower(Gdpr.email) == email.lower()))
        return result.scalar_one_or_none()

    async def upsert(self, user_id: UUID, email: str, legal_name: str = "") -> Gdpr:
        stmt = (
            pg_insert(Gdpr)
            .values(user_id=user_id, email=email, legal_name=legal_name)
            .on_conflict_do_update(
                index_elements=[Gdpr.user_id],
                set_={"email": email, "legal_name": legal_name, "updated_at": datetime.utcnow()},
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.get_by_user_id(user_id)  # type: ignore[return-value]


async def resolve_user_by_email(email: str, login_session: AsyncSession) -> User | None:
    """Look up a User via auth.gdpr. REQUIRES a login session."""
    result = await login_session.execute(
        select(User).join(Gdpr, User.user_id == Gdpr.user_id).where(func.lower(Gdpr.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def bootstrap_user(
    login_session: AsyncSession,
    app_session: AsyncSession,
    email: str,
    role: str = "user",
    legal_name: str = "",
    user_name: str | None = None,
) -> User:
    """Full bootstrap — creates auth.users + auth.gdpr (login session) and
    public.user_info + workspace (app session). Admin-only flow.
    """
    user = User(role=role)
    login_session.add(user)
    await login_session.flush()

    gdpr = Gdpr(user_id=user.user_id, email=email, legal_name=legal_name)
    login_session.add(gdpr)
    await login_session.commit()
    await login_session.refresh(user)

    handle = user_name or _slugify(email)
    user_info = UserInfo(user_id=user.user_id, user_name=handle)
    app_session.add(user_info)
    workspace = Workspace(workspace_name=email)
    app_session.add(workspace)
    await app_session.flush()
    member = WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role="owner")
    app_session.add(member)
    await app_session.commit()
    return user
