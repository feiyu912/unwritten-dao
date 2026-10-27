#!/usr/bin/env python3
"""Report the bounded world's endings from a deterministic simulation.

    uv run python -m tools.ending_report --days 365 --seed 42
    uv run python -m tools.ending_report --days 30 --seed 7 --json

Endings are derived from recorded events by ``world_core.evaluate_endings``;
nothing about the outcome is scripted. Use short horizons for quick checks and
longer ones only when the machine can afford them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from agent_runtime import RivalryPolicy, UtilityPolicy, decide_command
from world_core import (
    PLAYER_ID,
    CommandRejected,
    WorldEvent,
    WorldState,
    advance_time,
    apply_command,
    create_world,
    evaluate_endings,
    state_checksum,
    validate_state,
)


def simulate(
    *,
    days: int,
    seed: int,
    policy_name: str = "utility",
    intervene: Callable[[WorldState], None] | None = None,
) -> tuple[WorldState, list[WorldEvent]]:
    state = create_world(seed)
    if intervene is not None:
        intervene(state)
    if policy_name == "utility":
        policy = UtilityPolicy()
    elif policy_name == "rivalry":
        policy = RivalryPolicy()
    else:
        raise ValueError(f"unknown policy {policy_name}")
    events: list[WorldEvent] = []
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive or npc.active_action is not None:
                continue
            command = decide_command(state, npc.npc_id, policy)
            if command is None:
                continue
            try:
                result = apply_command(state, command)
            except CommandRejected:
                continue
            events.extend(result.events)
        events.extend(advance_time(state, 1).events)
    return state, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report endings from real events.")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--policy", choices=["utility", "rivalry"], default="utility")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    state, events = simulate(days=args.days, seed=args.seed, policy_name=args.policy)
    report = evaluate_endings(state, events)
    report["checksum"] = state_checksum(state)
    report["violations"] = validate_state(state)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        item = report["key_item"]
        conflict = report["core_conflict"]
        print(
            f"tick={report['tick']} checksum={report['checksum']} "
            f"violations={len(report['violations'])}"
        )
        print(
            f"key_item={item['item_id']} holder={item['holder_name']} "
            f"consumed_by={item['consumed_by']}"
        )
        print(
            f"realm_discovered={conflict['realm_discovered']} "
            f"realm_entered={conflict['realm_entered']} deaths={len(conflict['deaths'])}"
        )
        for ending in report["endings"]:
            print(
                f"- {ending['ending_id']}: {ending['summary']} "
                f"(evidence={ending['evidence_event_ids']})"
            )
    return 0 if not report["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())