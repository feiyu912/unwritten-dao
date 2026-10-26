"""R1 replay gate: seed plus command stream must reproduce an identical world."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from world_core import (
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    OPP_FOUNDATION_PILL,
    PROTAGONIST_ID,
    CommandType,
    WorldEvent,
    apply_command,
    create_world,
    make_command,
    state_checksum,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
EVENT_SCHEMA = json.loads(
    (ROOT / "docs" / "contracts" / "world-event.v1.schema.json").read_text(encoding="utf-8")
)
EVENT_VALIDATOR = Draft202012Validator(EVENT_SCHEMA, format_checker=FormatChecker())

RUNS = 100
SEED = 42

CommandIntent = tuple[CommandType, dict[str, Any], str | None]

# The canonical protagonist map path followed by a 30-day world advance.
COMMAND_SEQUENCE: tuple[CommandIntent, ...] = (
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
    ("move", {"to_location_id": LOC_ANCIENT_CAVE}, PROTAGONIST_ID),
    ("claim_opportunity", {"opportunity_id": OPP_FOUNDATION_PILL}, PROTAGONIST_ID),
    (
        "attempt_breakthrough",
        {"pill_item_id": ITEM_FOUNDATION_PILL},
        PROTAGONIST_ID,
    ),
    ("advance_time", {"ticks": 30}, None),
)


def _run_once() -> tuple[str, int, list[WorldEvent]]:
    """Execute the recorded intents against a fresh seed-42 world."""
    state = create_world(SEED)
    events: list[WorldEvent] = []
    for intent, arguments, actor_id in COMMAND_SEQUENCE:
        command = make_command(state, actor_id, intent, arguments, source="test")
        events.extend(apply_command(state, command).events)
    return state_checksum(state), len(events), events


def test_one_hundred_replay_runs_are_identical() -> None:
    results = [_run_once() for _ in range(RUNS)]
    expected_checksum, expected_events, _ = results[0]

    assert len(results) == RUNS
    for run, (checksum, event_count, _events) in enumerate(results, start=1):
        assert checksum == expected_checksum, (
            f"run {run}/{RUNS}: checksum {checksum} != {expected_checksum}"
        )
        assert event_count == expected_events, (
            f"run {run}/{RUNS}: {event_count} events != {expected_events} "
            f"(checksum {checksum})"
        )

    assert expected_checksum.startswith("sha256:")
    assert expected_events > 0


def test_replay_events_conform_to_the_world_event_contract() -> None:
    _checksum, _event_count, events = _run_once()

    assert events
    for event in events:
        EVENT_VALIDATOR.validate(event.model_dump(mode="json"))