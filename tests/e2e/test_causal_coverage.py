from __future__ import annotations

from tools.report_history import run


def test_important_outcomes_have_true_causal_parents() -> None:
    report = run(days=120, seed=42)
    assert report["violations"] == []
    assert report["important_events"] >= 1
    assert report["outcome_coverage"] >= 0.95, report
    assert report["coverage"] >= 0.95, report
    assert report["transfer_coverage"] >= 0.95, report
    assert report["checksum"].startswith("sha256:")


def test_moves_are_not_fake_causes_and_discovery_has_two_true_parents() -> None:
    from world_core import (
        ITEM_MAP_FRAGMENT,
        LOC_BLACKWOOD_FOREST,
        LOC_MISTY_VALLEY,
        LOC_RUINED_TEMPLE,
        PROTAGONIST_ID,
        apply_command,
        create_world,
        make_command,
    )

    state = create_world(42)
    events: dict[str, int] = {}

    def send(intent: str, arguments: dict[str, object]) -> list:
        result = apply_command(
            state,
            make_command(state, PROTAGONIST_ID, intent, arguments, source="test"),  # type: ignore[arg-type]
        )
        for event in result.events:
            events.setdefault(event.type, event.event_id)
            events[f"{event.type}:{event.event_id}"] = event.event_id
        return result.events

    send("move", {"to_location_id": LOC_BLACKWOOD_FOREST})
    second_move = send("move", {"to_location_id": LOC_RUINED_TEMPLE})
    assert second_move[0].causal_parent_ids == []

    transfer_events = send(
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": PROTAGONIST_ID},
        },
    )
    transfer_id = next(
        event.event_id for event in transfer_events if event.type == "ITEM_TRANSFERRED"
    )
    send("move", {"to_location_id": LOC_MISTY_VALLEY})
    investigated = send(
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
    )
    investigate_id = next(
        event.event_id for event in investigated if event.type == "LOCATION_INVESTIGATED"
    )
    discovery = next(event for event in investigated if event.type == "SECRET_REALM_DISCOVERED")
    assert set(discovery.causal_parent_ids) == {investigate_id, transfer_id}
