"""Cross-module acceptance test: a single early intervention changes the causal future.

The baseline lets the deterministic :class:`UtilityPolicy` play the protagonist from
the sect to the secret realm. The intervention moves the *player* to the temple at
tick 0 and lets them take the map fragment before the protagonist ever arrives.
"""

from __future__ import annotations

from agent_runtime import UtilityPolicy, decide_command
from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    OPP_FOUNDATION_PILL,
    PLAYER_ID,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    WorldEvent,
    WorldState,
    advance_time,
    apply_command,
    create_world,
    make_command,
    state_checksum,
    validate_state,
)

DAYS = 400
SEED = 42


def _run_protagonist(state: WorldState, days: int) -> list[WorldEvent]:
    """Ask the utility policy for one protagonist command per day, then advance a day."""
    policy = UtilityPolicy()
    events: list[WorldEvent] = []
    for _ in range(days):
        command = decide_command(state, PROTAGONIST_ID, policy)
        if command is not None:
            events.extend(apply_command(state, command).events)
        events.extend(advance_time(state, 1).events)
    return events


def _move_player_to_temple_and_take_map(state: WorldState) -> None:
    for target in (LOC_XUANYUE_SECT, LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        apply_command(
            state,
            make_command(
                state,
                PLAYER_ID,
                "move",
                {"to_location_id": target},
                source="test",
            ),
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


def test_baseline_protagonist_follows_the_map_path() -> None:
    state = create_world(SEED)
    events = _run_protagonist(state, DAYS)
    event_types = {event.type for event in events}
    protagonist = state.npcs[PROTAGONIST_ID]

    assert ITEM_MAP_FRAGMENT in protagonist.inventory
    assert PROTAGONIST_ID in state.secret_realms[REALM_ANCIENT_CAVE].discovered_by
    assert protagonist.location_id == LOC_ANCIENT_CAVE
    assert state.opportunities[OPP_FOUNDATION_PILL].claimed_by == PROTAGONIST_ID
    assert "BREAKTHROUGH_ATTEMPT" in event_types
    assert "SECRET_REALM_DISCOVERED" in event_types
    assert "OPPORTUNITY_CLAIMED" in event_types
    assert validate_state(state) == []


def test_player_taking_the_map_blocks_realm_discovery_and_claim() -> None:
    state = create_world(SEED)
    _move_player_to_temple_and_take_map(state)
    events = _run_protagonist(state, DAYS)

    player = state.npcs[PLAYER_ID]
    protagonist = state.npcs[PROTAGONIST_ID]
    realm = state.secret_realms[REALM_ANCIENT_CAVE]
    opportunity = state.opportunities[OPP_FOUNDATION_PILL]

    assert state.items[ITEM_MAP_FRAGMENT].owner_id == PLAYER_ID
    assert ITEM_MAP_FRAGMENT in player.inventory

    # Never owned, not merely not-owned-at-the-end: transfer events prove the map
    # never reaches the protagonist during the whole 400-day run.
    assert ITEM_MAP_FRAGMENT not in protagonist.inventory
    assert not any(
        event.type == "ITEM_TRANSFERRED"
        and event.payload.get("item_id") == ITEM_MAP_FRAGMENT
        and PROTAGONIST_ID in event.target_ids
        for event in events
    )

    assert realm.discovered_by == []
    assert not any(
        event.type in {"SECRET_REALM_DISCOVERED", "OPPORTUNITY_CLAIMED"}
        and PROTAGONIST_ID in event.actor_ids
        for event in events
    )
    assert opportunity.claimed_by is None
    assert protagonist.location_id != LOC_ANCIENT_CAVE
    assert validate_state(state) == []


def test_intervention_diverges_from_the_baseline_checksum() -> None:
    baseline = create_world(SEED)
    _run_protagonist(baseline, DAYS)

    intervention = create_world(SEED)
    _move_player_to_temple_and_take_map(intervention)
    _run_protagonist(intervention, DAYS)

    # The only difference is who holds the map before the temple is searched. The
    # protagonist can no longer discover the realm entrance, so the two worlds
    # must diverge even though they share seed and policy.
    assert state_checksum(baseline) != state_checksum(intervention)
