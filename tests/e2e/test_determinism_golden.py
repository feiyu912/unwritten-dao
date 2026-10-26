from __future__ import annotations

from world_core import (
    advance_time,
    apply_command,
    create_world,
    make_command,
    state_checksum,
)

# Cross-platform gate: this exact history must hash identically on macOS ARM64
# and Linux x86_64 (CI runs both). Changing simulation rules intentionally
# requires updating this golden value in the same PR.
GOLDEN_CHECKSUM = "sha256:0852e08b1b7294f6c6f5aa89f3a2a56106e0acad70da0bf5edee36b6eb520a19"


def test_twenty_year_rules_checksum_is_cross_platform_stable() -> None:
    state = create_world(42)
    for _year in range(20):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.alive and npc.active_action is None:
                apply_command(
                    state,
                    make_command(
                        state,
                        npc.npc_id,
                        "start_cultivation",
                        {"days": 365},
                        source="test",
                    ),
                )
        advance_time(state, 365)

    assert state.tick == 7300
    assert sum(1 for npc in state.npcs.values() if npc.alive) == 29
    assert state_checksum(state) == GOLDEN_CHECKSUM