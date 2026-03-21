# src/repository/user.py
from datetime import datetime

from sqlmodel import Session, select

from models.user import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: str) -> User | None:
        statement = select(User).where(User.user_id == user_id)
        return self.session.exec(statement).first()

    def create(self, user_id: str, role: str = "user") -> User:
        user = User(user_id=user_id, role=role)
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

    def get_or_create(self, user_id: str, role: str = "user") -> User:
        user = self.get_by_id(user_id)
        if user:
            return user
        return self.create(user_id, role)
