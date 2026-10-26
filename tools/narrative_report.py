#!/usr/bin/env python3
"""Generate a 20-year history analysis from a headless simulation.

    uv run python -m tools.narrative_report --years 20 --seed 42

Prints top events, causal chains, faction outcomes, and the protagonist's fate.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from agent_runtime import UtilityPolicy, decide_command
from world_core import (
    PLAYER_ID,
    advance_time,
    apply_command,
    create_world,
    state_checksum,
    validate_state,
)
from world_server.summaries import summarize_event

WEIGHT = {
    "NPC_DIED": 1.0,
    "BREAKTHROUGH_ATTEMPT": 0.9,
    "SECRET_REALM_DISCOVERED": 0.9,
    "OPPORTUNITY_CLAIMED": 0.8,
    "COMBAT_RESOLVED": 0.8,
    "SECRET_REALM_ENTERED": 0.7,
    "ITEM_TRANSFERRED": 0.5,
}


def _describe(state, event) -> str:
    actor = state.npcs.get(event.actor_ids[0]) if event.actor_ids else None
    who = actor.name if actor else "世界"
    return (
        f"[tick {event.tick:>4}] [E{event.event_id}] {who} "
        f"{event.type}: {summarize_event(event.type, event.payload, state)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="20-year narrative report.")
    parser.add_argument("--years", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    state = create_world(args.seed)
    policy = UtilityPolicy()
    events = {}
    type_counts: Counter[str] = Counter()
    for _ in range(args.years * 365):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive:
                continue
            command = decide_command(state, npc.npc_id, policy)
            if command is None:
                continue
            for event in apply_command(state, command).events:
                events[event.event_id] = event
                type_counts[event.type] += 1
        for event in advance_time(state, 1).events:
            events[event.event_id] = event
            type_counts[event.type] += 1

    important = sorted(
        (event for event in events.values() if event.type in WEIGHT),
        key=lambda event: (-WEIGHT[event.type], event.event_id),
    )
    print(f"# {args.years}-year history (seed={args.seed})")
    print(f"tick={state.tick} events={len(events)} checksum={state_checksum(state)}")
    print(f"violations={validate_state(state)}")
    print("\n## Top events")
    for event in important[:20]:
        print("- " + _describe(state, event))

    print("\n## Causal chains")
    for event in important[:5]:
        chain = []
        node = event
        seen = set()
        while node is not None and node.event_id not in seen and len(chain) < 8:
            seen.add(node.event_id)
            chain.append(node)
            node = events.get(node.causal_parent_ids[0]) if node.causal_parent_ids else None
        print(f"- E{event.event_id}:")
        for step in reversed(chain):
            print(f"    {_describe(state, step)}")

    print("\n## Factions")
    for faction in sorted(state.factions.values(), key=lambda item: item.faction_id):
        members = [npc for npc in state.npcs.values() if npc.faction_id == faction.faction_id]
        alive = sum(1 for npc in members if npc.alive)
        print(
            f"- {faction.name}: treasury={faction.treasury} "
            f"alive={alive}/{len(members)}"
        )

    protagonist = next(
        npc for npc in state.npcs.values() if npc.canonical_role == "protagonist"
    )
    print("\n## Protagonist")
    print(
        f"- {protagonist.name}: alive={protagonist.alive} realm={protagonist.realm} "
        f"location={protagonist.location_id} goals="
        f"{[(goal.kind, goal.status) for goal in protagonist.goals]}"
    )
    print("\n## Event counts")
    for name, count in type_counts.most_common(12):
        print(f"- {name}: {count}")
    return 0 if not validate_state(state) else 1


if __name__ == "__main__":
    sys.exit(main())