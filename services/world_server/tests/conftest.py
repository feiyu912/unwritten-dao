from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session
from world_server.db import get_engine, get_session_factory

SERVER_DIR = pathlib.Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.integration


def _run_migrations() -> None:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> Iterator[None]:
    _run_migrations()
    yield


@pytest.fixture()
def session() -> Iterator[Session]:
    factory = get_session_factory(get_engine())
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_tables(session: Session) -> Iterator[None]:
    session.execute(
        text(
            "TRUNCATE save, world_snapshot, command_log, event_edge, "
            "world_event, world_state, memory_episode, agent_decision CASCADE"
        )
    )
    session.commit()
    yield
