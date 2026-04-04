# src/repository/user.py
from datetime import datetime

from sqlmodel import Session, select

from models.user import User
from models.workspace import Workspace, WorkspaceMember


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.exec(statement).first()

    def create(self, email: str, role: str = "user") -> User:
        user = User(email=email, role=role)
        self.session.add(user)
        workspace = Workspace(workspace_id=email, name=email)
        self.session.add(workspace)
        member = WorkspaceMember(workspace_id=email, user_id=user.user_id, role="owner")
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
