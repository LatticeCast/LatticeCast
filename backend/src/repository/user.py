# src/repository/user.py
from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from models.user import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_uuid(self, uuid: UUID) -> User | None:
        return self.session.get(User, uuid)

    def get_by_id(self, id: str) -> User | None:
        statement = select(User).where(User.id == id)
        return self.session.exec(statement).first()

    def create(self, id: str, role: str = "user") -> User:
        user = User(id=id, role=role)
        self.session.add(user)
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

    def get_or_create(self, id: str, role: str = "user") -> User:
        user = self.get_by_id(id)
        if user:
            return user
        return self.create(id, role)
