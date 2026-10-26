#!/usr/bin/env python3
"""Seed PostgreSQL with an agent-driven history (default 20 years).

    uv run python -m tools.seed_history --years 20 --reset

This is an offline generation step; the live server still validates every
future command through world_core.
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import func, select, text
from world_server.db import get_engine, get_session_factory
from world_server.history import persist_history, reset_local_world, simulate_days
from world_server.models import MemoryEpisodeRow, WorldEventRow
from world_server.repository import bootstrap, load_state

from world_core import state_checksum, validate_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed an agent-driven world history.")
    parser.add_argument("--years", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true", help="truncate local tables first")
    args = parser.parse_args(argv)

    factory = get_session_factory(get_engine())
    session = factory()
    try:
        if args.reset:
            reset_local_world(session)
        bootstrap(session, seed=args.seed)
        state = load_state(session)
        started = time.perf_counter()
        events = simulate_days(state, args.years * 365)
        persist_history(session, state, events)
        elapsed = time.perf_counter() - started

        reloaded = load_state(session)
        event_count = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
        memory_count = session.execute(
            select(func.count()).select_from(MemoryEpisodeRow)
        ).scalar_one()
        db_bytes = int(
            session.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        )
        print(f"years={args.years} tick={reloaded.tick} elapsed={elapsed:.2f}s")
        print(f"events={event_count} memories={memory_count} db_bytes={db_bytes}")
        print(f"checksum={state_checksum(reloaded)}")
        print(f"violations={validate_state(reloaded)}")
        return 0 if not validate_state(reloaded) else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
