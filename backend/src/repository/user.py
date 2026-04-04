# src/repository/user.py
import re
from datetime import datetime

from sqlmodel import Session, select

from models.user import User, UserInfo
from models.workspace import Workspace, WorkspaceMember


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9._@/-]", "-", text.lower())
    slug = re.sub(r"^[^a-z0-9]+", "", slug)
    return slug[:128] or "workspace"


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.exec(statement).first()

    def create(self, email: str, role: str = "user") -> User:
        user = User(email=email, role=role)
        self.session.add(user)
        self.session.flush()  # get user_id assigned
        display_id = _slugify(email)
        user_info = UserInfo(user_id=user.user_id, display_id=display_id, email=email, name="")
        self.session.add(user_info)
        workspace = Workspace(name=email, display_id=display_id)
        self.session.add(workspace)
        self.session.flush()  # get workspace_id assigned
        member = WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role="owner")
        self.session.add(member)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: User, role: str | None = None) -> User:
        if role:
            user.role = role
        user.updated_at = datetime.utcnow()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_or_create(self, email: str, role: str = "user") -> User:
        user = self.get_by_email(email)
        if user:
            return user
        return self.create(email, role)
