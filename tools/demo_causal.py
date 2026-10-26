#!/usr/bin/env python3
"""Headless demo: watch one stolen map rewrite the protagonist's fate.

Runs the same seed twice, once untouched and once with the player taking the
map before the protagonist can see it, and prints the causal timeline.

    uv run python -m tools.demo_causal --days 400
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from agent_runtime import UtilityPolicy, decide_command
from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_BLACKWOOD_FOREST,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    OPP_FOUNDATION_PILL,
    PLAYER_ID,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    advance_time,
    apply_command,
    create_world,
    make_command,
    state_checksum,
    validate_state,
)

KEY_EVENTS = {
    "ITEM_TRANSFERRED": "取得物品",
    "SECRET_REALM_DISCOVERED": "发现秘境",
    "SECRET_REALM_ENTERED": "进入秘境",
    "OPPORTUNITY_CLAIMED": "机缘",
    "BREAKTHROUGH_ATTEMPT": "尝试突破",
    "NPC_DIED": "身死",
}


@dataclass
class Timeline:
    lines: list[str] = field(default_factory=list)
    checksum: str = ""
    protagonist_outcome: dict[str, object] = field(default_factory=dict)

    def add(self, state, events) -> None:
        for event in events:
            if event.type not in KEY_EVENTS:
                continue
            actor = state.npcs.get(event.actor_ids[0]) if event.actor_ids else None
            who = actor.name if actor else "世界"
            if event.type == "BREAKTHROUGH_ATTEMPT":
                detail = f"→ 境界 {event.payload.get('to_realm')} " + (
                    "成功" if event.payload.get("success") else "失败"
                )
            elif event.type == "NPC_DIED":
                detail = f"（{event.payload.get('cause')}）"
            else:
                detail = event.payload.get("name") or event.payload.get("realm_id") or ""
            self.lines.append(f"  第 {state.tick:>4} 天 {who} {KEY_EVENTS[event.type]} {detail}")


def _steal_map(state) -> None:
    player = state.npcs[PLAYER_ID]
    for target in (LOC_XUANYUE_SECT, LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        command = make_command(
            state, PLAYER_ID, "move", {"to_location_id": target}, source="player"
        )
        apply_command(state, command)
    apply_command(
        state,
        make_command(
            state,
            PLAYER_ID,
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": player.npc_id},
            },
            source="player",
        ),
    )


def run(*, days: int, steal: bool) -> Timeline:
    state = create_world(42)
    timeline = Timeline()
    if steal:
        _steal_map(state)
    policy = UtilityPolicy()
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive:
                continue
            command = decide_command(state, npc.npc_id, policy)
            if command is not None:
                timeline.add(state, apply_command(state, command).events)
        result = advance_time(state, 1)
        timeline.add(state, result.events)
        if not state.npcs[PROTAGONIST_ID].alive:
            break
    protagonist = state.npcs[PROTAGONIST_ID]
    timeline.checksum = state_checksum(state)
    timeline.protagonist_outcome = {
        "alive": protagonist.alive,
        "death_cause": protagonist.death_cause,
        "realm": protagonist.realm,
        "location": protagonist.location_id,
        "has_map": ITEM_MAP_FRAGMENT in protagonist.inventory,
        "owns_pill": "item_foundation_pill" in protagonist.inventory,
        "realm_discovered": protagonist.npc_id
        in state.secret_realms[REALM_ANCIENT_CAVE].discovered_by,
        "pill_claimed_by": state.opportunities[OPP_FOUNDATION_PILL].claimed_by,
    }
    assert validate_state(state) == [], validate_state(state)
    return timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Causal divergence demo.")
    parser.add_argument("--days", type=int, default=400)
    args = parser.parse_args(argv)

    baseline = run(days=args.days, steal=False)
    print("BASELINE — 主角自行取得残图")
    print("\n".join(baseline.lines[:12]) or "  (no key events)")
    print(f"  outcome: {baseline.protagonist_outcome}")
    print(f"  checksum: {baseline.checksum}")

    stolen = run(days=args.days, steal=True)
    print("\nINTERVENTION — 玩家在主角之前取走残图")
    print("\n".join(stolen.lines[:12]) or "  (no key events)")
    print(f"  outcome: {stolen.protagonist_outcome}")
    print(f"  checksum: {stolen.checksum}")

    diverged = baseline.checksum != stolen.checksum
    print(f"\nDIVERGED: {diverged}")
    return 0 if diverged else 1


if __name__ == "__main__":
    sys.exit(main())
