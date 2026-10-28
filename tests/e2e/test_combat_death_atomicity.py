"""Regression: lethal damage must resolve death in the same command.

Every setup step below is a recorded world command from ``create_world(42)``;
no test code writes NPC health, location, inventory, or death state directly.
"""

from __future__ import annotations

import pytest
from world_core.worldgen import ITEM_SPIRIT_SWORD, npc_id

from world_core import (
    LOC_BLACKWOOD_FOREST,
    CommandRejected,
    apply_command,
    create_world,
    make_command,
    state_checksum,
    validate_state,
)

LU_XUANJI = npc_id("lu_xuanji")
PEI_LIE = npc_id("pei_lie")


def _run(state, commands, events, actor_id, command_type, arguments):
    command = make_command(state, actor_id, command_type, arguments, source="test")
    result = apply_command(state, command)
    commands.append(command)
    events.extend(result.events)
    return result


def _colocate(state, commands, events):
    attacker = state.npcs[LU_XUANJI]
    victim = state.npcs[PEI_LIE]
    _run(
        state,
        commands,
        events,
        LU_XUANJI,
        "move",
        {"to_location_id": LOC_BLACKWOOD_FOREST},
    )
    _run(
        state,
        commands,
        events,
        PEI_LIE,
        "move",
        {"to_location_id": LOC_BLACKWOOD_FOREST},
    )
    assert attacker.location_id == LOC_BLACKWOOD_FOREST
    assert victim.location_id == LOC_BLACKWOOD_FOREST
    return attacker, victim


def _attack(state, commands, events, target_id, intent):
    result = _run(
        state,
        commands,
        events,
        LU_XUANJI,
        "attack",
        {"target_id": target_id, "intent": intent},
    )
    combat = next(event for event in result.events if event.type == "COMBAT_RESOLVED")
    return result, combat


def _fight_until_death(state, commands, events, attacker, victim, intent):
    for _ in range(20):
        assert attacker.alive
        assert victim.alive
        assert victim.health > 0.0
        health_before = victim.health
        result, combat = _attack(state, commands, events, victim.npc_id, intent)
        if victim.health == 0.0:
            assert victim.alive is False
        if not victim.alive:
            deaths = [event for event in result.events if event.type == "NPC_DIED"]
            assert len(deaths) == 1
            return combat, deaths[0], health_before
    pytest.fail(f"{victim.npc_id} survived 20 {intent} attacks")


def _assert_unique_ownership(state):
    holders: dict[str, set[str]] = {}
    for npc in state.npcs.values():
        assert len(set(npc.inventory)) == len(npc.inventory)
        for item_id in npc.inventory:
            holders.setdefault(item_id, set()).add(npc.npc_id)
            assert state.items[item_id].owner_id == npc.npc_id
    assert all(len(npc_ids) == 1 for npc_ids in holders.values())

    stashes: dict[str, set[str]] = {}
    for location in state.locations.values():
        assert len(set(location.stash)) == len(location.stash)
        for item_id in location.stash:
            stashes.setdefault(item_id, set()).add(location.location_id)

    # Non-unique owner-only baseline entries are outside unique-item coverage;
    # carried non-unique items are still checked in the first pass above.
    for item in state.items.values():
        if not item.unique:
            continue
        item_holders = holders.get(item.item_id, set())
        item_stashes = stashes.get(item.item_id, set())
        if item.owner_id is not None:
            assert item_holders == {item.owner_id}
            assert item.location_id is None
            assert item.hidden is False
            assert item_stashes == set()
        elif item.hidden:
            assert item_holders == set()
            assert item.location_id is None
            assert item_stashes == set()
        else:
            assert item_holders == set()
            assert item.location_id is not None
            assert item_stashes == {item.location_id}


def _assert_dead_actor_rejected(state):
    checksum = state_checksum(state)
    version = state.state_version
    with pytest.raises(CommandRejected) as error:
        apply_command(
            state,
            make_command(
                state,
                PEI_LIE,
                "move",
                {"to_location_id": LOC_BLACKWOOD_FOREST},
                source="test",
            ),
        )
    assert error.value.code == "actor_dead"
    assert state_checksum(state) == checksum
    assert state.state_version == version


def _assert_replay(commands, events, state):
    replay = create_world(42)
    replay_events = []
    for command in commands:
        replay_events.extend(apply_command(replay, command).events)
    assert state_checksum(replay) == state_checksum(state)
    assert [event.model_dump(mode="json") for event in replay_events] == [
        event.model_dump(mode="json") for event in events
    ]


@pytest.mark.parametrize("intent", ["subdue", "rob"])
def test_damage_to_zero_kills_in_same_command_and_replays(intent):
    state = create_world(42)
    commands = []
    events = []
    attacker, victim = _colocate(state, commands, events)

    combat, death, health_before = _fight_until_death(
        state, commands, events, attacker, victim, intent
    )

    assert health_before > 0.0
    assert combat.payload["intent"] == intent
    assert combat.payload["attacker_won"] is True
    assert combat.payload["defender_died"] is True
    assert death.actor_ids == [victim.npc_id]
    assert death.causal_parent_ids == [combat.event_id]
    assert death.payload["cause"] == "combat"
    assert death.payload["killer_id"] == attacker.npc_id
    assert victim.alive is False
    assert victim.health == 0.0
    assert victim.death_cause == "combat"
    assert victim.death_tick == state.tick
    assert validate_state(state) == []
    _assert_unique_ownership(state)
    if intent == "rob":
        assert state.items[ITEM_SPIRIT_SWORD].owner_id == attacker.npc_id
        assert ITEM_SPIRIT_SWORD in attacker.inventory
        assert ITEM_SPIRIT_SWORD not in victim.inventory

    _assert_dead_actor_rejected(state)
    _assert_replay(commands, events, state)


def test_kill_intent_keeps_existing_early_threshold_and_causal_death():
    state = create_world(42)
    commands = []
    events = []
    attacker, victim = _colocate(state, commands, events)

    for _ in range(20):
        assert attacker.alive
        assert victim.alive
        health_before = victim.health
        result, combat = _attack(state, commands, events, victim.npc_id, "kill")
        if not victim.alive:
            deaths = [event for event in result.events if event.type == "NPC_DIED"]
            assert len(deaths) == 1
            death = deaths[0]
            assert combat.payload["attacker_won"] is True
            assert combat.payload["defender_died"] is True
            assert health_before > 0.15
            assert round(health_before - combat.payload["damage"], 6) <= 0.15
            assert death.causal_parent_ids == [combat.event_id]
            assert death.payload["cause"] == "combat"
            assert death.payload["killer_id"] == attacker.npc_id
            assert victim.health == 0.0
            break
    else:
        pytest.fail("kill did not reach the existing 0.15 threshold")

    assert validate_state(state) == []
    _assert_unique_ownership(state)
    _assert_dead_actor_rejected(state)
    _assert_replay(commands, events, state)
