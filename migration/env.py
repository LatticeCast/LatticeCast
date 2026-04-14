import os

sqlalchemy_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://dba_user:dba_pws@db:5432/db",
)
