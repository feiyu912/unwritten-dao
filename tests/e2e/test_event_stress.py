from __future__ import annotations

import time

import pytest

from world_core import (
    LOC_STONE_TOWN,
    LOC_XUANYUE_SECT,
    PLAYER_ID,
    apply_command,
    create_world,
    make_command,
    state_checksum,
    validate_state,
)

TARGET_EVENTS = 100_000


@pytest.mark.slow
def test_hundred_thousand_events_keep_invariants() -> None:
    state = create_world(42)
    a, b = LOC_STONE_TOWN, LOC_XUANYUE_SECT
    started = time.perf_counter()
    for index in range(TARGET_EVENTS):
        target = b if index % 2 == 0 else a
        command = make_command(state, PLAYER_ID, "move", {"to_location_id": target}, source="test")
        result = apply_command(state, command)
        assert len(result.events) == 1
    elapsed = time.perf_counter() - started

    assert state.state_version == TARGET_EVENTS
    assert state.last_event_id == TARGET_EVENTS
    assert validate_state(state) == []
    checksum = state_checksum(state)
    assert checksum.startswith("sha256:")
    print(
        f"\n{TARGET_EVENTS} events in {elapsed:.2f}s "
        f"({TARGET_EVENTS / elapsed:,.0f} events/s), checksum {checksum}"
    )
    assert elapsed < 300
