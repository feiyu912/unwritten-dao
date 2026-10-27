from __future__ import annotations

from tools.ending_report import simulate

from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    PLAYER_ID,
    PROTAGONIST_ID,
    Relationship,
    WorldEvent,
    WorldState,
    advance_time,
    apply_command,
    create_world,
    evaluate_endings,
    genesis_events,
    make_command,
    npc_id,
    relationship_key,
    state_checksum,
)

PILL_FATES = {"pill_ascension", "pill_wasted", "pill_held", "pill_dormant"}
REALM_FATES = {"realm_opened", "realm_found", "realm_sealed"}


def _take_map_at_temple(state: WorldState) -> list[WorldEvent]:
    events: list[WorldEvent] = []
    for target in (LOC_XUANYUE_SECT, LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        events.extend(
            apply_command(
                state,
                make_command(
                    state, PLAYER_ID, "move", {"to_location_id": target}, source="test"
                ),
            ).events
        )
    events.extend(
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
        ).events
    )
    return events


def _steal_map_at_tick_zero(state: WorldState) -> None:
    _take_map_at_temple(state)


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


def _kill(
    state: WorldState, attacker_id: str, target_id: str, events: list[WorldEvent]
) -> None:
    for _ in range(20):
        if not state.npcs[target_id].alive:
            return
        assert state.npcs[attacker_id].alive, f"{attacker_id} died before {target_id}"
        result = apply_command(
            state,
            make_command(
                state,
                attacker_id,
                "attack",
                {"target_id": target_id, "intent": "kill"},
                source="test",
            ),
        )
        events.extend(result.events)
    raise AssertionError(f"{target_id} survived 20 kill attempts")


def test_revenge_ending_opens_then_resolves() -> None:
    state = create_world(42)
    killer = state.npcs[npc_id("lu_xuanji")]
    victim = state.npcs[npc_id("a_he")]
    survivor = state.npcs[npc_id("su_zhi")]
    healer = state.npcs[PROTAGONIST_ID]
    victim.location_id = LOC_XUANYUE_SECT
    victim.health = 0.01
    healer.location_id = LOC_XUANYUE_SECT
    healer.realm = 6
    healer.stage = 4
    healer.foundation = 1.0
    healer.health = 1.0
    state.relationships[relationship_key(survivor.npc_id, victim.npc_id)] = Relationship(
        source_npc_id=survivor.npc_id,
        target_npc_id=victim.npc_id,
        affinity=25,
    )
    events: list[WorldEvent] = []

    _kill(state, killer.npc_id, victim.npc_id, events)
    opened = {
        ending["ending_id"] for ending in evaluate_endings(state, events)["endings"]
    }
    assert "blood_feud_open" in opened

    _kill(state, healer.npc_id, killer.npc_id, events)
    events.extend(advance_time(state, 1).events)
    report = evaluate_endings(state, events)
    ids = {ending["ending_id"] for ending in report["endings"]}

    assert "blood_feud_resolved" in ids
    resolved = next(e for e in report["endings"] if e["ending_id"] == "blood_feud_resolved")
    assert resolved["evidence_event_ids"]
    assert set(resolved["evidence_event_ids"]) <= {event.event_id for event in events}
    killer_deaths = {
        event.event_id
        for event in events
        if event.type == "NPC_DIED" and killer.npc_id in event.actor_ids
    }
    assert killer_deaths
    assert killer_deaths <= set(resolved["evidence_event_ids"])


def test_entering_the_realm_opens_the_ending() -> None:
    state = create_world(42)
    events = _take_map_at_temple(state)
    events.extend(
        apply_command(
            state,
            make_command(
                state,
                PLAYER_ID,
                "move",
                {"to_location_id": LOC_MISTY_VALLEY},
                source="test",
            ),
        ).events
    )
    events.extend(
        apply_command(
            state,
            make_command(
                state,
                PLAYER_ID,
                "investigate",
                {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
                source="test",
            ),
        ).events
    )
    realm_id = next(iter(state.secret_realms))
    events.extend(
        apply_command(
            state,
            make_command(
                state, PLAYER_ID, "enter_secret_realm", {"realm_id": realm_id}, source="test"
            ),
        ).events
    )

    report = evaluate_endings(state, events)

    ids = {ending["ending_id"] for ending in report["endings"]}
    assert "realm_opened" in ids
    opened = next(e for e in report["endings"] if e["ending_id"] == "realm_opened")
    entered_ids = {event.event_id for event in events if event.type == "SECRET_REALM_ENTERED"}
    assert entered_ids
    assert entered_ids <= set(opened["evidence_event_ids"])

    # A snapshot without its event log (e.g. after loading a save) must still
    # report the realm as opened from the state's own event references.
    bare = evaluate_endings(state, [])
    bare_opened = next(e for e in bare["endings"] if e["ending_id"] == "realm_opened")
    assert entered_ids <= set(bare_opened["evidence_event_ids"])


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