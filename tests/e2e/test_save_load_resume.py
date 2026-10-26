"""Cross-module acceptance test: snapshot, restore, and resume without divergence."""

from __future__ import annotations

import json
from typing import Any

from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    OPP_FOUNDATION_PILL,
    PROTAGONIST_ID,
    CommandType,
    WorldEvent,
    WorldState,
    apply_command,
    create_world,
    make_command,
    restore_snapshot,
    snapshot,
    state_checksum,
)

SEED = 42
SAVE_TICK = 10
END_TICK = 20

Stream = tuple[tuple[CommandType, dict[str, Any], str | None], ...]

# Moves and advances that leave the protagonist at the realm entrance at tick 10.
PRE_SAVE_STREAM: Stream = (
    ("move", {"to_location_id": LOC_BLACKWOOD_FOREST}, PROTAGONIST_ID),
    ("move", {"to_location_id": LOC_RUINED_TEMPLE}, PROTAGONIST_ID),
    (
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": PROTAGONIST_ID},
        },
        PROTAGONIST_ID,
    ),
    ("move", {"to_location_id": LOC_MISTY_VALLEY}, PROTAGONIST_ID),
    (
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        PROTAGONIST_ID,
    ),
    ("advance_time", {"ticks": 5}, None),
    ("advance_time", {"ticks": 5}, None),
)

# Commands issued after the save point: enter, claim, then advance to tick 20.
POST_SAVE_STREAM: Stream = (
    ("move", {"to_location_id": LOC_ANCIENT_CAVE}, PROTAGONIST_ID),
    ("claim_opportunity", {"opportunity_id": OPP_FOUNDATION_PILL}, PROTAGONIST_ID),
    ("advance_time", {"ticks": 4}, None),
    ("advance_time", {"ticks": 6}, None),
)


def _apply_stream(state: WorldState, stream: Stream) -> list[WorldEvent]:
    events: list[WorldEvent] = []
    for intent, arguments, actor_id in stream:
        command = make_command(state, actor_id, intent, arguments, source="test")
        events.extend(apply_command(state, command).events)
    return events


def test_save_load_resume_matches_the_original_future() -> None:
    state = create_world(SEED)
    _apply_stream(state, PRE_SAVE_STREAM)
    assert state.tick == SAVE_TICK

    saved = snapshot(state)

    post_save_commands = []
    continued_events: list[WorldEvent] = []
    for intent, arguments, actor_id in POST_SAVE_STREAM:
        command = make_command(state, actor_id, intent, arguments, source="test")
        post_save_commands.append(command)
        continued_events.extend(apply_command(state, command).events)

    assert state.tick == END_TICK
    checksum_a = state_checksum(state)
    event_types_a = [event.type for event in continued_events]
    assert checksum_a != saved["checksum"]

    # Restore through a JSON round trip, as the persistence layer would.
    restored = restore_snapshot(json.loads(json.dumps(saved)))
    assert restored.tick == saved["tick"]
    assert restored.state_version == saved["state_version"]
    assert restored.last_event_id == saved["last_event_id"]
    assert state_checksum(restored) == saved["checksum"]
    assert snapshot(restored)["checksum"] == saved["checksum"]

    replayed_events: list[WorldEvent] = []
    for command in post_save_commands:
        replayed_events.extend(apply_command(restored, command).events)

    checksum_b = state_checksum(restored)
    event_types_b = [event.type for event in replayed_events]

    assert restored.tick == END_TICK
    assert checksum_b == checksum_a, f"resume checksum {checksum_b} != {checksum_a}"
    assert event_types_b == event_types_a