from __future__ import annotations

import json
import pathlib
import time

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from world_core import (
    FACTION_XUANYUE,
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_STONE_TOWN,
    OPP_FOUNDATION_PILL,
    PLAYER_ID,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    CommandRejected,
    advance_time,
    apply_command,
    create_world,
    make_command,
    restore_snapshot,
    snapshot,
    state_checksum,
    validate_state,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = json.loads(
    (ROOT / "docs" / "contracts" / "world-event.v1.schema.json").read_text(encoding="utf-8")
)
EVENT_VALIDATOR = Draft202012Validator(CONTRACT, format_checker=FormatChecker())


def _run_scenario(seed: int = 42) -> tuple[str, list[str]]:
    state = create_world(seed)
    actor = state.npcs[PROTAGONIST_ID]
    event_types: list[str] = []

    def send(command_type: str, arguments: dict[str, object]) -> None:
        command = make_command(state, actor.npc_id, command_type, arguments, source="test")  # type: ignore[arg-type]
        result = apply_command(state, command)
        event_types.extend(event.type for event in result.events)
        for event in result.events:
            EVENT_VALIDATOR.validate(event.model_dump(mode="json"))

    send("move", {"to_location_id": LOC_BLACKWOOD_FOREST})
    send("move", {"to_location_id": LOC_RUINED_TEMPLE})
    send(
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": actor.npc_id},
        },
    )
    send("move", {"to_location_id": LOC_MISTY_VALLEY})
    send("investigate", {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"})
    send("move", {"to_location_id": LOC_ANCIENT_CAVE})
    send("claim_opportunity", {"opportunity_id": OPP_FOUNDATION_PILL})
    send("attempt_breakthrough", {"pill_item_id": ITEM_FOUNDATION_PILL})
    advance_time(state, 30)
    return state_checksum(state), event_types


def test_seed_world_is_valid_and_deterministic() -> None:
    first = create_world(42)
    second = create_world(42)

    assert len(first.npcs) == 30
    assert first.npcs[PLAYER_ID].canonical_role == "player"
    assert validate_state(first) == []
    assert state_checksum(first) == state_checksum(second)


def test_identical_commands_produce_identical_state_and_events() -> None:
    first_checksum, first_events = _run_scenario(42)
    second_checksum, second_events = _run_scenario(42)

    assert first_checksum == second_checksum
    assert first_events == second_events
    assert "BREAKTHROUGH_ATTEMPT" in first_events
    assert "SECRET_REALM_DISCOVERED" in first_events


def test_stale_state_version_is_rejected() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    command = make_command(
        state, actor.npc_id, "move", {"to_location_id": LOC_BLACKWOOD_FOREST}, source="test"
    )
    apply_command(state, command)

    with pytest.raises(CommandRejected) as error:
        apply_command(state, command)
    assert error.value.code == "stale_state_version"
    assert validate_state(state) == []


def test_dead_npc_cannot_act() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    actor.alive = False
    actor.health = 0.0
    actor.death_tick = state.tick
    command = make_command(
        state, actor.npc_id, "move", {"to_location_id": LOC_BLACKWOOD_FOREST}, source="test"
    )

    with pytest.raises(CommandRejected) as error:
        apply_command(state, command)
    assert error.value.code == "actor_dead"


def test_unique_item_cannot_have_two_owners() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    actor.location_id = LOC_RUINED_TEMPLE
    command = make_command(
        state,
        actor.npc_id,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": actor.npc_id},
        },
        source="test",
    )
    apply_command(state, command)

    with pytest.raises(CommandRejected) as error:
        apply_command(
            state,
            make_command(
                state,
                actor.npc_id,
                "transfer_item",
                {
                    "item_id": ITEM_MAP_FRAGMENT,
                    "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                    "to": {"kind": "npc", "id": actor.npc_id},
                },
                source="test",
            ),
        )
    assert error.value.code == "item_not_there"
    assert validate_state(state) == []


def test_snapshot_round_trip() -> None:
    state = create_world(42)
    doc = snapshot(state)
    restored = restore_snapshot(json.loads(json.dumps(doc)))

    assert state_checksum(state) == state_checksum(restored)
    assert restored.model_dump(mode="json") == state.model_dump(mode="json")


def test_twenty_year_headless_run_stays_valid() -> None:
    state = create_world(42)
    started = time.perf_counter()
    events_seen = 0

    for _year in range(20):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.alive and npc.active_action is None:
                command = make_command(
                    state, npc.npc_id, "start_cultivation", {"days": 365}, source="test"
                )
                events_seen += len(apply_command(state, command).events)
        result = advance_time(state, 365)
        events_seen += len(result.events)

    elapsed = time.perf_counter() - started
    assert state.tick == 7300
    assert validate_state(state) == []
    assert elapsed < 600, f"20-year headless run took {elapsed:.2f}s"
    assert events_seen > 500

    for event in result.events:
        EVENT_VALIDATOR.validate(event.model_dump(mode="json"))


def test_without_map_the_realm_stays_undiscovered() -> None:
    state = create_world(42)
    actor = state.npcs[PROTAGONIST_ID]
    actor.location_id = LOC_MISTY_VALLEY
    investigate = make_command(
        state,
        actor.npc_id,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        source="test",
    )
    apply_command(state, investigate)

    assert state.secret_realms[REALM_ANCIENT_CAVE].discovered_by == []
    with pytest.raises(CommandRejected) as error:
        apply_command(
            state,
            make_command(
                state,
                actor.npc_id,
                "move",
                {"to_location_id": LOC_ANCIENT_CAVE},
                source="test",
            ),
        )
    assert error.value.code == "realm_undiscovered"


def test_combat_resolves_and_keeps_invariants() -> None:
    from world_core.worldgen import npc_id

    from world_core import LOC_XUANYUE_SECT

    state = create_world(42)
    attacker = state.npcs[PROTAGONIST_ID]
    target = state.npcs[npc_id("pei_lie")]
    target.location_id = LOC_XUANYUE_SECT
    before = {attacker.npc_id: attacker.health, target.npc_id: target.health}

    command = make_command(
        state,
        attacker.npc_id,
        "attack",
        {"target_id": target.npc_id, "intent": "rob"},
        source="test",
    )
    result = apply_command(state, command)
    combat = next(event for event in result.events if event.type == "COMBAT_RESOLVED")
    assert 0.0 <= combat.payload["probability"] <= 1.0
    assert 0.0 <= combat.payload["roll"] <= 1.0
    assert validate_state(state) == []
    changed = (
        attacker.health != before[attacker.npc_id]
        or target.health != before[target.npc_id]
        or not target.alive
        or not attacker.alive
    )
    assert changed


def test_attack_requires_co_location() -> None:
    from world_core.worldgen import npc_id

    state = create_world(42)
    attacker = state.npcs[PROTAGONIST_ID]
    target = state.npcs[npc_id("pei_lie")]
    with pytest.raises(CommandRejected) as error:
        apply_command(
            state,
            make_command(
                state,
                attacker.npc_id,
                "attack",
                {"target_id": target.npc_id, "intent": "kill"},
                source="test",
            ),
        )
    assert error.value.code == "target_not_present"


def test_faction_economy_settles_every_thirty_days() -> None:
    state = create_world(42)
    faction = state.factions[FACTION_XUANYUE]
    before = faction.treasury
    members = sum(1 for npc in state.npcs.values() if npc.faction_id == FACTION_XUANYUE)
    advance_time(state, 30)
    expected = before + faction.income_per_30d - faction.upkeep_per_member * members
    assert faction.treasury == expected


def test_natural_death_clears_action_and_blocks_commands() -> None:
    from world_core.worldgen import npc_id

    state = create_world(42)
    victim = state.npcs[npc_id("a_he")]
    victim.birth_tick = -victim.lifespan_ticks + 1
    apply_command(
        state,
        make_command(state, victim.npc_id, "start_cultivation", {"days": 30}, source="test"),
    )
    result = advance_time(state, 1)
    assert any(event.type == "NPC_DIED" for event in result.events)
    assert victim.alive is False
    assert victim.active_action is None
    assert validate_state(state) == []

    with pytest.raises(CommandRejected) as error:
        apply_command(
            state,
            make_command(
                state,
                victim.npc_id,
                "move",
                {"to_location_id": LOC_STONE_TOWN},
                source="test",
            ),
        )
    assert error.value.code == "actor_dead"


def test_secret_realm_closes_and_opportunity_expires() -> None:
    state = create_world(42)
    events = advance_time(state, 3650).events + advance_time(state, 1826).events
    realm = state.secret_realms[REALM_ANCIENT_CAVE]
    opportunity = state.opportunities[OPP_FOUNDATION_PILL]
    assert realm.opened is False
    assert opportunity.expired is True
    types = [event.type for event in events]
    assert "SECRET_REALM_CLOSED" in types
    assert "OPPORTUNITY_EXPIRED" in types
    assert validate_state(state) == []
