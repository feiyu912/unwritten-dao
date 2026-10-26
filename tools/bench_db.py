#!/usr/bin/env python3
"""Persist a 20-year history through PostgreSQL and report size/latency.

    EMBEDDING_PROVIDER=off DATABASE_URL=... uv run python -m tools.bench_db --reset

--reset truncates the local development tables first.
"""

from __future__ import annotations

import argparse
import time

from sqlalchemy import func, select, text
from world_server.db import get_engine, get_session_factory
from world_server.models import (
    AgentDecisionRow,
    MemoryEpisodeRow,
    WorldEventRow,
)
from world_server.repository import apply_command, bootstrap, load_state

from world_core import make_command, state_checksum, validate_state


def _truncate(session) -> None:
    session.execute(
        text(
            "TRUNCATE save, world_snapshot, command_log, event_edge, "
            "world_event, world_state, memory_episode, agent_decision CASCADE"
        )
    )
    session.commit()


def _relation_bytes(session, name: str) -> int:
    return int(
        session.execute(text("SELECT pg_total_relation_size(:name)"), {"name": name}).scalar_one()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persisted 20-year benchmark.")
    parser.add_argument("--years", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true", help="truncate local tables first")
    args = parser.parse_args(argv)

    factory = get_session_factory(get_engine())
    session = factory()
    if args.reset:
        _truncate(session)
    bootstrap(session, seed=args.seed)

    started = time.perf_counter()
    for _year in range(args.years):
        initial = load_state(session)
        for npc_id in sorted(initial.npcs):
            state = load_state(session)
            npc = state.npcs[npc_id]
            if npc.alive and npc.active_action is None:
                apply_command(
                    session,
                    make_command(
                        state,
                        npc.npc_id,
                        "start_cultivation",
                        {"days": 365},
                        source="system",
                        idempotency_key=f"bench:{npc.npc_id}:{state.tick}:cultivate",
                    ),
                )
        state = load_state(session)
        command = make_command(
            state,
            None,
            "advance_time",
            {"ticks": 365},
            source="system",
            idempotency_key=f"bench:advance:{state.tick}",
        )
        apply_command(session, command)
    elapsed = time.perf_counter() - started

    state = load_state(session)
    events = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    memories = session.execute(select(func.count()).select_from(MemoryEpisodeRow)).scalar_one()
    decisions = session.execute(select(func.count()).select_from(AgentDecisionRow)).scalar_one()
    sizes = {
        "world_state": _relation_bytes(session, "world_state"),
        "world_event": _relation_bytes(session, "world_event"),
        "memory_episode": _relation_bytes(session, "memory_episode"),
        "database": int(
            session.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        ),
    }
    session.close()

    print(f"years={args.years} tick={state.tick} elapsed={elapsed:.2f}s")
    print(f"events={events} memories={memories} decisions={decisions}")
    for name, size in sizes.items():
        print(f"{name}_bytes={size}")
    print(f"checksum={state_checksum(state)}")
    print(f"violations={validate_state(state)}")
    return 0 if not validate_state(state) else 1


if __name__ == "__main__":
    raise SystemExit(main())
