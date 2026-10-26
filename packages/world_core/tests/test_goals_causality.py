from __future__ import annotations

import json

from world_core import (
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    OPP_FOUNDATION_PILL,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    Goal,
    Relationship,
    WorldState,
    advance_time,
    apply_breakthrough_goal_progress,
    apply_command,
    apply_death_goal_evolution,
    create_world,
    make_command,
    npc_id,
    relationship_key,
    restore_snapshot,
    snapshot,
    validate_state,
)


def _send(state: WorldState, actor_id: str, command_type: str, arguments: dict[str, object]):
    return apply_command(
        state,
        make_command(state, actor_id, command_type, arguments, source="test"),  # type: ignore[arg-type]
    )


def test_causal_provenance_of_map_discovery_entry_claim_and_breakthrough() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    move_ids: list[int] = []

    moved = _send(state, actor.npc_id, "move", {"to_location_id": LOC_BLACKWOOD_FOREST})
    move_ids.extend(event.event_id for event in moved.events if event.type == "NPC_MOVED")
    moved = _send(state, actor.npc_id, "move", {"to_location_id": LOC_RUINED_TEMPLE})
    move_ids.extend(event.event_id for event in moved.events if event.type == "NPC_MOVED")

    transferred = _send(
        state,
        actor.npc_id,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": actor.npc_id},
        },
    )
    transfer_event = next(event for event in transferred.events if event.type == "ITEM_TRANSFERRED")
    assert transfer_event.causal_parent_ids == []
    assert state.items[ITEM_MAP_FRAGMENT].acquired_event_id == transfer_event.event_id

    moved = _send(state, actor.npc_id, "move", {"to_location_id": LOC_MISTY_VALLEY})
    move_ids.extend(event.event_id for event in moved.events if event.type == "NPC_MOVED")

    investigated = _send(
        state,
        actor.npc_id,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
    )
    investigate_event = next(
        event for event in investigated.events if event.type == "LOCATION_INVESTIGATED"
    )
    discovery_event = next(
        event for event in investigated.events if event.type == "SECRET_REALM_DISCOVERED"
    )
    assert investigate_event.causal_parent_ids == []
    # Two true causes: the investigation and the event that granted the map.
    assert discovery_event.causal_parent_ids == sorted(
        {investigate_event.event_id, transfer_event.event_id}
    )
    realm = state.secret_realms[REALM_ANCIENT_CAVE]
    assert realm.discovery_event_ids[actor.npc_id] == discovery_event.event_id

    entered = _send(
        state, actor.npc_id, "enter_secret_realm", {"realm_id": REALM_ANCIENT_CAVE}
    )
    entry_event = next(event for event in entered.events if event.type == "SECRET_REALM_ENTERED")
    assert entry_event.causal_parent_ids == [discovery_event.event_id]
    assert realm.entry_event_ids[actor.npc_id] == entry_event.event_id
    assert actor.location_id == LOC_ANCIENT_CAVE

    claimed = _send(
        state, actor.npc_id, "claim_opportunity", {"opportunity_id": OPP_FOUNDATION_PILL}
    )
    claim_event = next(event for event in claimed.events if event.type == "OPPORTUNITY_CLAIMED")
    assert claim_event.causal_parent_ids == [entry_event.event_id]
    assert (
        state.items[ITEM_FOUNDATION_PILL].acquired_event_id == claim_event.event_id
    )

    brewed = _send(
        state,
        actor.npc_id,
        "attempt_breakthrough",
        {"pill_item_id": ITEM_FOUNDATION_PILL},
    )
    attempt_event = next(
        event for event in brewed.events if event.type == "BREAKTHROUGH_ATTEMPT"
    )
    consume_event = next(event for event in brewed.events if event.type == "ITEM_CONSUMED")
    assert consume_event.causal_parent_ids == [claim_event.event_id]
    assert attempt_event.causal_parent_ids == sorted(
        {claim_event.event_id, consume_event.event_id}
    )

    # No event above may cite a merely previous movement as its cause.
    for event in (
        investigate_event,
        discovery_event,
        entry_event,
        claim_event,
        consume_event,
        attempt_event,
    ):
        assert set(event.causal_parent_ids).isdisjoint(move_ids)
    assert validate_state(state) == []


def test_death_creates_one_revenge_goal_and_resolves_rival_goal() -> None:
    state = create_world(42)
    killer = state.npcs[npc_id("lu_xuanji")]
    victim = state.npcs[npc_id("a_he")]
    survivor = state.npcs[npc_id("su_zhi")]
    rival = state.npcs[PROTAGONIST_ID]

    victim.location_id = LOC_XUANYUE_SECT
    victim.health = 0.01
    state.relationships[relationship_key(survivor.npc_id, victim.npc_id)] = Relationship(
        source_npc_id=survivor.npc_id,
        target_npc_id=victim.npc_id,
        affinity=25,
    )
    rival.goals.append(
        Goal(
            goal_id="goal_test_defeat_a_he",
            kind="defeat_rival",
            priority=0.9,
            params={"target_id": victim.npc_id},
        )
    )

    death_event = None
    for _ in range(5):
        if not victim.alive:
            break
        result = _send(
            state,
            killer.npc_id,
            "attack",
            {"target_id": victim.npc_id, "intent": "kill"},
        )
        death_event = next(
            (event for event in result.events if event.type == "NPC_DIED"), death_event
        )

    assert victim.alive is False
    assert death_event is not None
    assert death_event.payload["killer_id"] == killer.npc_id

    revenges = [goal for goal in survivor.goals if goal.kind == "revenge"]
    assert len(revenges) == 1
    revenge = revenges[0]
    assert revenge.status == "active"
    assert revenge.params["target_id"] == killer.npc_id
    assert revenge.origin_event_id == death_event.event_id
    assert revenge.last_updated_tick == state.tick

    rival_goal = next(goal for goal in rival.goals if goal.goal_id == "goal_test_defeat_a_he")
    assert rival_goal.status == "achieved"
    assert rival_goal.last_updated_tick == state.tick

    # Replaying the same death event must not duplicate the revenge goal.
    before = [goal.goal_id for goal in survivor.goals]
    apply_death_goal_evolution(
        state,
        victim,
        death_event_id=death_event.event_id,
        killer_id=killer.npc_id,
    )
    assert [goal.goal_id for goal in survivor.goals] == before
    assert validate_state(state) == []


def test_long_term_goal_survives_many_ticks_and_snapshot_restore() -> None:
    state = create_world(42)
    goal_ids = {goal.goal_id for goal in state.npcs[PROTAGONIST_ID].goals}
    assert "goal_breakthrough" in goal_ids

    for _ in range(100):
        advance_time(state, 3)
    assert state.tick == 300

    protagonist = state.npcs[PROTAGONIST_ID]
    assert {goal.goal_id for goal in protagonist.goals} == goal_ids
    breakthrough = next(goal for goal in protagonist.goals if goal.goal_id == "goal_breakthrough")
    assert breakthrough.status == "active"

    restored = restore_snapshot(json.loads(json.dumps(snapshot(state))))
    restored_goal_ids = {goal.goal_id for goal in restored.npcs[PROTAGONIST_ID].goals}
    assert restored_goal_ids == goal_ids
    restored_breakthrough = next(
        goal
        for goal in restored.npcs[PROTAGONIST_ID].goals
        if goal.goal_id == "goal_breakthrough"
    )
    assert restored_breakthrough.status == "active"
    assert restored_breakthrough.created_tick == breakthrough.created_tick
    assert validate_state(restored) == []


def test_validator_accepts_provenance_and_rejects_future_ids() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    actor.location_id = LOC_RUINED_TEMPLE
    transferred = _send(
        state,
        actor.npc_id,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": actor.npc_id},
        },
    )
    transfer_id = next(
        event.event_id for event in transferred.events if event.type == "ITEM_TRANSFERRED"
    )
    item = state.items[ITEM_MAP_FRAGMENT]
    assert item.acquired_event_id == transfer_id
    assert validate_state(state) == []

    item.acquired_event_id = state.last_event_id + 1
    assert any("future acquisition event id" in problem for problem in validate_state(state))
    item.acquired_event_id = transfer_id

    goal = actor.goals[0]
    goal.last_updated_tick = state.tick + 1
    assert any("future last_updated_tick" in problem for problem in validate_state(state))
    goal.last_updated_tick = None
    assert validate_state(state) == []

    # Old snapshots without provenance fields still deserialize with defaults.
    document = state.model_dump(mode="json")
    for item_document in document["items"].values():
        item_document.pop("acquired_event_id", None)
    for realm_document in document["secret_realms"].values():
        realm_document.pop("discovery_event_ids", None)
        realm_document.pop("entry_event_ids", None)
    for npc_document in document["npcs"].values():
        for goal_document in npc_document["goals"]:
            goal_document.pop("origin_event_id", None)
            goal_document.pop("last_updated_tick", None)
    restored = WorldState.model_validate(document)
    assert restored.items[ITEM_MAP_FRAGMENT].acquired_event_id is None
    assert restored.npcs[PROTAGONIST_ID].goals[0].origin_event_id is None
    assert restored.secret_realms[REALM_ANCIENT_CAVE].entry_event_ids == {}
    assert validate_state(restored) == []


def test_breakthrough_goal_records_origin_and_update_tick() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    goal = next(goal for goal in actor.goals if goal.goal_id == "goal_breakthrough")
    actor.realm = int(goal.params["target_realm"])
    actor.stage = 1
    actor.qi = 0
    advance_time(state, 1)

    achieved = apply_breakthrough_goal_progress(
        actor, event_id=state.last_event_id, tick=state.tick
    )

    assert achieved == ["goal_breakthrough"]
    assert goal.status == "achieved"
    assert goal.origin_event_id == state.last_event_id
    assert goal.last_updated_tick == state.tick
    assert validate_state(state) == []