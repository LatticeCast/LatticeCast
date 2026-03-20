# src/repository/table.py
from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from models.table import Table


class TableRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, user_id: str, name: str) -> Table:
        table = Table(user_id=user_id, name=name)
        self.session.add(table)
        self.session.commit()
        self.session.refresh(table)
        return table

    def get_by_id(self, table_id: UUID) -> Table | None:
        return self.session.get(Table, table_id)

    def list_by_user(self, user_id: str) -> list[Table]:
        statement = select(Table).where(Table.user_id == user_id)
        return list(self.session.exec(statement).all())

    def update(self, table: Table, name: str) -> Table:
        table.name = name
        table.updated_at = datetime.utcnow()
        self.session.add(table)
        self.session.commit()
        self.session.refresh(table)
        return table

    def delete(self, table: Table) -> None:
        self.session.delete(table)
        self.session.commit()
