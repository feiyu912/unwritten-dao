#!/usr/bin/env python3
"""Print one character's life timeline from a simulated history.

uv run python -m tools.character_history --npc 沈砚 --years 20
"""

from __future__ import annotations

import argparse
import sys

from world_server.summaries import summarize_event

from agent_runtime import RivalryPolicy, decide_command
from world_core import (
    PLAYER_ID,
    advance_time,
    apply_command,
    create_world,
    genesis_events,
    state_checksum,
    validate_state,
)

NOISE = {
    "CULTIVATION_STARTED",
    "CULTIVATION_COMPLETED",
    "WORLD_ADVANCED",
    "FACTION_UPDATED",
    "RELATIONSHIP_CHANGED",
}


def simulate(*, years: int, seed: int):
    state = create_world(seed)
    policy = RivalryPolicy()
    events = list(genesis_events(state))
    for _ in range(years * 365):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive:
                continue
            command = decide_command(state, npc.npc_id, policy)
            if command is None:
                continue
            events.extend(apply_command(state, command).events)
        events.extend(advance_time(state, 1).events)
    return state, events


def find_npc(state, query: str):
    for npc in state.npcs.values():
        if query in {npc.npc_id, npc.name, npc.canonical_role}:
            return npc
    for npc in state.npcs.values():
        if query in npc.name or npc.npc_id.startswith(query):
            return npc
    return None


def character_timeline(state, events, npc_id: str) -> list[str]:
    lines: list[str] = []
    for event in sorted(events, key=lambda item: item.event_id):
        if npc_id not in event.actor_ids and npc_id not in event.target_ids:
            continue
        if event.type in NOISE:
            continue
        lines.append(
            f"[tick {event.tick:>4}] [E{event.event_id}] {event.type}: "
            f"{summarize_event(event.type, event.payload, state)}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One character's life timeline.")
    parser.add_argument("--npc", default="protagonist", help="name, role, or npc id")
    parser.add_argument("--years", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    state, events = simulate(years=args.years, seed=args.seed)
    npc = find_npc(state, args.npc)
    if npc is None:
        print(f"unknown character: {args.npc}")
        return 2

    print(f"# {npc.name} — {args.years} years (seed={args.seed})")
    print(
        f"alive={npc.alive} realm={npc.realm} stage={npc.stage} "
        f"location={npc.location_id} lifespan={npc.lifespan_ticks}"
    )
    print(f"goals={[(goal.kind, goal.status) for goal in npc.goals]}")
    print(f"violations={validate_state(state)} checksum={state_checksum(state)}")
    print("\n## Life events")
    timeline = character_timeline(state, events, npc.npc_id)
    for line in timeline[:80]:
        print("- " + line)
    if len(timeline) > 80:
        print(f"- ... {len(timeline) - 80} more events")
    return 0 if not validate_state(state) else 1


if __name__ == "__main__":
    sys.exit(main())
