from __future__ import annotations

import json

from world_core import (
    advance_time,
    apply_command,
    create_world,
    make_command,
    restore_snapshot,
    snapshot,
    state_checksum,
    validate_state,
)


def _run_years(state, years: int) -> None:
    for _ in range(years):
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


def test_save_at_year_ten_and_resume_to_twenty_matches_uninterrupted_run() -> None:
    uninterrupted = create_world(42)
    _run_years(uninterrupted, 10)
    save = json.loads(json.dumps(snapshot(uninterrupted)))
    _run_years(uninterrupted, 10)
    expected_checksum = state_checksum(uninterrupted)
    expected_event_id = uninterrupted.last_event_id

    restored = restore_snapshot(save)
    assert restored.tick == 3650
    _run_years(restored, 10)

    assert state_checksum(restored) == expected_checksum
    assert restored.last_event_id == expected_event_id
    assert validate_state(restored) == []
