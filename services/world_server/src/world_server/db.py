"""SQLAlchemy engine/session wiring."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from world_server.config import SETTINGS


@lru_cache(maxsize=1)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or SETTINGS.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_dependency() -> Iterator[Session]:
    factory = get_session_factory(get_engine())
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
