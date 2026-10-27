from __future__ import annotations

from tools.ending_report import simulate

from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_BLACKWOOD_FOREST,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    PLAYER_ID,
    WorldState,
    apply_command,
    create_world,
    evaluate_endings,
    genesis_events,
    make_command,
    state_checksum,
)

PILL_FATES = {"pill_ascension", "pill_wasted", "pill_held", "pill_dormant"}
REALM_FATES = {"realm_opened", "realm_found", "realm_sealed"}


def _steal_map_at_tick_zero(state: WorldState) -> None:
    for target in (LOC_XUANYUE_SECT, LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        apply_command(
            state,
            make_command(state, PLAYER_ID, "move", {"to_location_id": target}, source="test"),
        )
    apply_command(
        state,
        make_command(
            state,
            PLAYER_ID,
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": PLAYER_ID},
            },
            source="test",
        ),
    )


def test_fresh_world_has_sealed_realm_and_hidden_pill() -> None:
    state = create_world(42)
    report = evaluate_endings(state, genesis_events(state))

    ids = {ending["ending_id"] for ending in report["endings"]}
    assert "pill_dormant" in ids
    assert "realm_sealed" in ids
    assert report["core_conflict"]["deaths"] == []
    assert report["evidence_event_ids"] == []


def test_endings_are_traceable_and_read_only() -> None:
    state, events = simulate(days=120, seed=42)
    before = state_checksum(state)

    report = evaluate_endings(state, events)

    assert state_checksum(state) == before
    assert report["schema_version"] == "ending-report.v1"
    assert report["tick"] == state.tick
    ids = {ending["ending_id"] for ending in report["endings"]}
    assert len(ids & PILL_FATES) == 1
    assert len(ids & REALM_FATES) == 1
    known = {event.event_id for event in events}
    assert set(report["evidence_event_ids"]) <= known
    for ending in report["endings"]:
        assert set(ending["evidence_event_ids"]) <= known


def test_stealing_the_map_changes_the_ending() -> None:
    baseline_state, baseline_events = simulate(days=60, seed=42)
    baseline_report = evaluate_endings(baseline_state, baseline_events)
    baseline = {ending["ending_id"] for ending in baseline_report["endings"]}
    cut_state, cut_events = simulate(
        days=60, seed=42, intervene=_steal_map_at_tick_zero
    )
    cut = {ending["ending_id"] for ending in evaluate_endings(cut_state, cut_events)["endings"]}

    assert "realm_found" in baseline
    assert "pill_ascension" in baseline
    assert "realm_sealed" in cut
    assert "pill_dormant" in cut
    assert baseline != cut