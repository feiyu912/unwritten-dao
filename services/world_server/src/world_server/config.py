"""World server configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    world_seed: int

    @staticmethod
    def from_env() -> Settings:
        return Settings(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/unwritten_dao",
            ),
            world_seed=int(os.environ.get("WORLD_SEED", "42")),
        )


SETTINGS = Settings.from_env()
