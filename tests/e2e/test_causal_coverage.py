from __future__ import annotations

from tools.report_history import run


def test_important_events_have_causal_parents() -> None:
    report = run(days=120, seed=42)
    assert report["violations"] == []
    assert report["important_events"] >= 1
    assert report["coverage"] >= 0.95, report["coverage"]
    assert report["checksum"].startswith("sha256:")


def test_npc_last_event_chains_commands() -> None:
    from world_core import (
        LOC_BLACKWOOD_FOREST,
        LOC_RUINED_TEMPLE,
        PROTAGONIST_ID,
        apply_command,
        create_world,
        make_command,
    )

    state = create_world(42)
    first = apply_command(
        state,
        make_command(
            state,
            PROTAGONIST_ID,
            "move",
            {"to_location_id": LOC_BLACKWOOD_FOREST},
            source="test",
        ),
    )
    actor = state.npcs[PROTAGONIST_ID]
    assert actor.last_event_id == first.events[0].event_id

    second = apply_command(
        state,
        make_command(
            state,
            PROTAGONIST_ID,
            "move",
            {"to_location_id": LOC_RUINED_TEMPLE},
            source="test",
        ),
    )
    assert second.events[0].causal_parent_ids == [first.events[0].event_id]
