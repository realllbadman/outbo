from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

engine_args = {"connect_args": {"check_same_thread": False}}
if settings.database_url == "sqlite://":
    # Tests use an in-memory database, which only exists on a single connection.
    engine_args["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **engine_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
