from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


NPC_A = "11111111-1111-4111-8111-111111111111"
NPC_B = "22222222-2222-4222-8222-222222222222"
WORLD = "33333333-3333-4333-8333-333333333333"
COMMAND = "44444444-4444-4444-8444-444444444444"

COMMAND_EXAMPLE = {
    "schema_version": "world-command.v1",
    "command_id": COMMAND,
    "idempotency_key": "player:take-map:1",
    "world_id": WORLD,
    "actor_id": NPC_A,
    "issued_tick": 12,
    "expected_state_version": 7,
    "type": "transfer_item",
    "arguments": {
        "item_id": "item_map_fragment",
        "from": {"kind": "location", "id": "ruined_temple"},
        "to": {"kind": "npc", "id": NPC_A},
    },
    "source": "player",
}

EVENT_EXAMPLE = {
    "schema_version": "world-event.v1",
    "event_id": 92135,
    "world_id": WORLD,
    "tick": 189230,
    "type": "BREAKTHROUGH_ATTEMPT",
    "actor_ids": [NPC_A],
    "target_ids": [],
    "location_id": "cave_interior",
    "causal_parent_ids": [91881, 92110],
    "rng_seed": 778193294,
    "command_id": COMMAND,
    "state_version_after": 8,
    "payload": {
        "from_realm": 1,
        "to_realm": 2,
        "pill_id": "item_foundation_pill",
        "probability": 0.67,
        "roll": 0.413,
        "success": True,
    },
}

SNAPSHOT_EXAMPLE = {
    "schema_version": "world-snapshot.v1",
    "world_id": WORLD,
    "tick": 0,
    "last_event_id": 0,
    "state_version": 0,
    "world_seed": 42,
    "sim_version": "0.1.0",
    "ruleset_version": "1.0.0",
    "checksum": "sha256:" + "0" * 64,
    "state": {},
}

OBSERVATION_EXAMPLE = {
    "schema_version": "npc-observation.v1",
    "npc_id": NPC_A,
    "tick": 12,
    "world_version": 7,
    "location_id": "qingyun_sect",
    "self": {
        "name": "沈砚",
        "realm": 1,
        "stage": 8,
        "qi": 1820,
        "foundation": 0.7,
        "health": 0.95,
        "wealth": 40,
        "lifespan_ticks": 43800,
        "birth_tick": -6570,
        "estimated_remaining_life_ticks": 37230,
        "traits": {"caution": 0.8},
    },
    "inventory": [{"item_id": "item_map_fragment", "name": "残破洞府图", "kind": "map"}],
    "visible_items": [],
    "visible_opportunities": [],
    "visible_npcs": [{"npc_id": NPC_B, "name": "苏芷", "realm": 2, "stage": 2, "alive": True}],
    "relationships": [
        {"npc_id": NPC_B, "affinity": 10, "trust": 20, "fear": 0, "respect": 15, "debt": 0}
    ],
    "beliefs": [
        {
            "subject_key": "misty_valley",
            "predicate": "has_secret_realm",
            "object_value": True,
            "confidence": 0.72,
            "source_event_id": 100,
        }
    ],
    "known_locations": [
        {
            "location_id": "qingyun_sect",
            "name": "玄岳宗",
            "kind": "sect",
            "adjacent_ids": ["stone_town", "blackwood_forest"],
        }
    ],
    "memories": [
        {
            "event_id": 100,
            "tick": 10,
            "summary": "在破庙拾得残图。",
            "importance": 0.8,
            "emotional_valence": 0.4,
        }
    ],
    "recent_events": [
        {"event_id": 100, "tick": 10, "type": "ITEM_TRANSFERRED", "summary": "拾得残图"}
    ],
    "goals": [
        {
            "goal_id": "goal_breakthrough",
            "kind": "breakthrough",
            "status": "active",
            "priority": 1.0,
        }
    ],
    "active_action": None,
    "available_actions": ["wait", "move", "start_cultivation", "investigate"],
}

PROPOSAL_EXAMPLE = {
    "schema_version": "action-proposal.v1",
    "proposal_id": "55555555-5555-4555-8555-555555555555",
    "decision_id": "d-01928",
    "npc_id": NPC_A,
    "observed_world_version": 7,
    "goal_id": "goal_breakthrough",
    "intent": "move",
    "arguments": {"to_location_id": "ruined_temple"},
    "valid_for_ticks": 7,
    "memory_refs": [100],
    "rationale_short": "洞府图在破庙，先去取图。",  # noqa: RUF001
    "confidence": 0.82,
}


@pytest.mark.parametrize("name", sorted(p.name for p in CONTRACTS.glob("*.schema.json")))
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    Draft202012Validator.check_schema(_load(name))


@pytest.mark.parametrize(
    ("name", "example"),
    [
        ("world-command.v1.schema.json", COMMAND_EXAMPLE),
        ("world-event.v1.schema.json", EVENT_EXAMPLE),
        ("world-snapshot.v1.schema.json", SNAPSHOT_EXAMPLE),
        ("npc-observation.v1.schema.json", OBSERVATION_EXAMPLE),
        ("action-proposal.v1.schema.json", PROPOSAL_EXAMPLE),
    ],
)
def test_examples_match_contracts(name: str, example: dict) -> None:
    _validator(name).validate(example)


def test_command_requires_actor_except_time_advance() -> None:
    validator = _validator("world-command.v1.schema.json")
    bad = {**COMMAND_EXAMPLE, "actor_id": None}
    assert list(validator.iter_errors(bad)), "non-system command must have an actor"

    advance = {
        **COMMAND_EXAMPLE,
        "actor_id": None,
        "type": "advance_time",
        "arguments": {"ticks": 1},
    }
    assert not list(validator.iter_errors(advance))


def test_unknown_command_field_rejected() -> None:
    validator = _validator("world-command.v1.schema.json")
    bad = {**COMMAND_EXAMPLE, "created_by_llm": True}
    assert list(validator.iter_errors(bad))


def test_ruleset_and_openapi_parse() -> None:
    ruleset = yaml.safe_load((CONTRACTS / "ruleset.v1.yaml").read_text(encoding="utf-8"))
    assert ruleset["schema_version"] == "ruleset.v1"
    assert len(ruleset["realms"]) >= 4
    assert ruleset["world"]["npc_count"] == 30

    api = yaml.safe_load((CONTRACTS / "api.openapi.yaml").read_text(encoding="utf-8"))
    assert api["openapi"].startswith("3.1")
    assert "/v1/commands" in api["paths"]
