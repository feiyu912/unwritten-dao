#!/usr/bin/env python3
"""Report causal coverage and goal outcomes over a simulated history.

    uv run python -m tools.report_history --days 400 --seed 42

Important events are those that change lives: transfers, discoveries,
claims, breakthroughs, combat, and death. Coverage is the share with at
least one recorded causal parent.
"""

from __future__ import annotations

import argparse
import sys

from agent_runtime import UtilityPolicy, decide_command
from world_core import (
    PLAYER_ID,
    advance_time,
    apply_command,
    create_world,
    state_checksum,
    validate_state,
)

IMPORTANT = {
    "ITEM_TRANSFERRED",
    "SECRET_REALM_DISCOVERED",
    "SECRET_REALM_ENTERED",
    "OPPORTUNITY_CLAIMED",
    "BREAKTHROUGH_ATTEMPT",
    "COMBAT_RESOLVED",
    "NPC_DIED",
}


def run(*, days: int, seed: int) -> dict[str, object]:
    state = create_world(seed)
    policy = UtilityPolicy()
    important_records: list[tuple[str, bool]] = []
    event_types: dict[str, int] = {}
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive:
                continue
            command = decide_command(state, npc.npc_id, policy)
            if command is None:
                continue
            result = apply_command(state, command)
            for event in result.events:
                event_types[event.type] = event_types.get(event.type, 0) + 1
                if event.type in IMPORTANT:
                    important_records.append((event.type, bool(event.causal_parent_ids)))
        result = advance_time(state, 1)
        for event in result.events:
            event_types[event.type] = event_types.get(event.type, 0) + 1
            if event.type in IMPORTANT:
                important_records.append((event.type, bool(event.causal_parent_ids)))
    protagonist = state.npcs[
        next(npc.npc_id for npc in state.npcs.values() if npc.canonical_role == "protagonist")
    ]
    important = len(important_records)
    covered = sum(1 for _, has_parent in important_records if has_parent)
    coverage = (covered / important) if important else 1.0
    outcomes = [record for record in important_records if record[0] != "ITEM_TRANSFERRED"]
    outcome_covered = sum(1 for _, has_parent in outcomes if has_parent)
    outcome_coverage = (outcome_covered / len(outcomes)) if outcomes else 1.0
    transfers = [record for record in important_records if record[0] == "ITEM_TRANSFERRED"]
    transfer_covered = sum(1 for _, has_parent in transfers if has_parent)
    transfer_coverage = (transfer_covered / len(transfers)) if transfers else 1.0
    goal_counts: dict[str, int] = {}
    for npc in state.npcs.values():
        for goal in npc.goals:
            goal_counts[goal.status] = goal_counts.get(goal.status, 0) + 1
    resolved = sum(goal_counts.get(status, 0) for status in ("achieved", "failed", "abandoned"))
    persistence = (goal_counts.get("achieved", 0) / resolved) if resolved else None
    return {
        "tick": state.tick,
        "important_events": important,
        "covered_events": covered,
        "coverage": round(coverage, 4),
        "outcome_coverage": round(outcome_coverage, 4),
        "transfer_coverage": round(transfer_coverage, 4),
        "goals": [(goal.kind, goal.status) for goal in protagonist.goals],
        "goal_counts": goal_counts,
        "resolved_goal_persistence": persistence,
        "protagonist_alive": protagonist.alive,
        "protagonist_realm": protagonist.realm,
        "checksum": state_checksum(state),
        "top_event_types": sorted(event_types.items(), key=lambda item: -item[1])[:8],
        "violations": validate_state(state),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Causal coverage report.")
    parser.add_argument("--days", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    report = run(days=args.days, seed=args.seed)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0 if not report["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
