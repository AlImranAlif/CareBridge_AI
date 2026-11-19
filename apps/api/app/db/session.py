from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_database_engine(database_url: str) -> Engine:
    return create_database_engine(database_url)


def get_session_factory() -> sessionmaker[Session] | None:
    url = get_settings().database_url
    if not url:
        return None
    return sessionmaker(bind=get_database_engine(url), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database is not configured")
    with factory() as session:
        yield session
