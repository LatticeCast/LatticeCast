# src/repository/user.py
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User, UserInfo
from models.workspace import Workspace, WorkspaceMember


def _slugify(text: str) -> str:
    """Convert text to a display_id matching ^[a-z0-9][a-z0-9_-]{2,31}$."""
    slug = re.sub(r"[^a-z0-9_-]", "-", text.lower())
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"^[^a-z0-9]+", "", slug)
    slug = slug[:32].rstrip("-")
    if len(slug) < 3:
        slug = (slug + "---")[:3]
    return slug


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, role: str = "user") -> User:
        user = User(email=email, role=role)
        self.session.add(user)
        await self.session.flush()  # get user_id assigned
        display_id = _slugify(email)
        user_info = UserInfo(user_id=user.user_id, display_id=display_id, email=email, name="")
        self.session.add(user_info)
        workspace = Workspace(name=email, display_id=display_id)
        self.session.add(workspace)
        await self.session.flush()  # get workspace_id assigned
        member = WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role="owner")
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user: User, role: str | None = None) -> User:
        if role:
            user.role = role
        user.updated_at = datetime.utcnow()
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_or_create(self, email: str, role: str = "user") -> User:
        user = await self.get_by_email(email)
        if user:
            return user
        return await self.create(email, role)
