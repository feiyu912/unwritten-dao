from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from agent_runtime.models import ActionProposal, NpcObservation
from agent_runtime.observation import build_observation
from agent_runtime.validator import ProposalRejected, decide_command
from jsonschema import Draft202012Validator, FormatChecker
from world_core.models import WorldState

from world_core import (
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    PLAYER_ID,
    PROTAGONIST_ID,
    apply_command,
    create_world,
    make_command,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = json.loads(
    (ROOT / "docs" / "contracts" / "npc-observation.v1.schema.json").read_text(encoding="utf-8")
)
OBSERVATION_VALIDATOR = Draft202012Validator(CONTRACT, format_checker=FormatChecker())


def _validate(observation: NpcObservation) -> None:
    OBSERVATION_VALIDATOR.validate(observation.model_dump(mode="json"))


def _send(state: WorldState, command_type: str, arguments: dict[str, Any]) -> None:
    command = make_command(
        state,
        PROTAGONIST_ID,
        command_type,  # type: ignore[arg-type]
        arguments,
        source="test",
    )
    apply_command(state, command)


def _discover_realm(state: WorldState) -> None:
    _send(state, "move", {"to_location_id": LOC_BLACKWOOD_FOREST})
    _send(state, "move", {"to_location_id": LOC_RUINED_TEMPLE})
    _send(
        state,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": PROTAGONIST_ID},
        },
    )
    _send(state, "move", {"to_location_id": LOC_MISTY_VALLEY})
    _send(
        state,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
    )


class _StubPolicy:
    """Returns a fixed proposal, corrupted on request, and counts calls."""

    def __init__(
        self,
        *,
        npc_id: str = PROTAGONIST_ID,
        version_offset: int = 0,
        intent: str = "start_cultivation",
        arguments: dict[str, Any] | None = None,
    ) -> None:
        self.calls = 0
        self.npc_id = npc_id
        self.version_offset = version_offset
        self.intent = intent
        self.arguments = arguments if arguments is not None else {"days": 30}

    def decide(self, observation: NpcObservation) -> ActionProposal:
        self.calls += 1
        return ActionProposal(
            proposal_id="00000000-0000-4000-8000-000000000001",
            decision_id=f"stub:{self.intent}",
            npc_id=self.npc_id,
            observed_world_version=observation.world_version + self.version_offset,
            intent=self.intent,  # type: ignore[arg-type]
            arguments=dict(self.arguments),
            valid_for_ticks=7,
            rationale_short="stub proposal",
            confidence=0.5,
        )


def test_initial_observation_matches_contract_and_hides_secrets() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)

    _validate(observation)
    assert observation.schema_version == "npc-observation.v1"
    assert observation.location_id == state.npcs[PROTAGONIST_ID].location_id
    assert [row.item_id for row in observation.inventory] == ["item_talisman"]
    assert len(observation.available_actions) == 9

    known = {row.location_id for row in observation.known_locations}
    assert LOC_ANCIENT_CAVE not in known
    for row in observation.known_locations:
        assert LOC_ANCIENT_CAVE not in row.adjacent_ids

    serialized = json.dumps(observation.model_dump(mode="json"), ensure_ascii=False)
    assert LOC_ANCIENT_CAVE not in serialized
    assert ITEM_FOUNDATION_PILL not in serialized
    assert not any(item.item_id == ITEM_FOUNDATION_PILL for item in observation.visible_items)


def test_hidden_pill_is_never_a_visible_item() -> None:
    state = create_world(42)
    npc = state.npcs[PROTAGONIST_ID]
    npc.location_id = LOC_ANCIENT_CAVE
    npc.known_locations.append(LOC_ANCIENT_CAVE)

    observation = build_observation(state, PROTAGONIST_ID)

    _validate(observation)
    assert [item.item_id for item in observation.visible_items] == []
    assert [row.opportunity_id for row in observation.visible_opportunities] == [
        "opp_foundation_pill"
    ]


def test_secret_interior_appears_only_after_map_and_investigation() -> None:
    state = create_world(42)
    _discover_realm(state)

    observation = build_observation(state, PROTAGONIST_ID)

    _validate(observation)
    known = {row.location_id: row for row in observation.known_locations}
    assert LOC_ANCIENT_CAVE in known
    assert LOC_ANCIENT_CAVE in known[LOC_MISTY_VALLEY].adjacent_ids
    assert LOC_ANCIENT_CAVE in state.npcs[PROTAGONIST_ID].known_locations


@pytest.mark.parametrize(
    ("npc_id", "version_offset"),
    [
        (PLAYER_ID, 0),
        (PROTAGONIST_ID, 1),
    ],
)
def test_invalid_proposal_falls_back_exactly_once(
    npc_id: str, version_offset: int
) -> None:
    state = create_world(42)
    bad = _StubPolicy(npc_id=npc_id, version_offset=version_offset)
    fallback = _StubPolicy()

    command = decide_command(state, PROTAGONIST_ID, bad, fallback=fallback)

    assert bad.calls == 1
    assert fallback.calls == 1
    assert command is not None
    assert command.type == "start_cultivation"
    assert command.actor_id == PROTAGONIST_ID
    assert command.source == "agent"
    apply_command(state, command)


def test_proposal_for_unknown_npc_is_rejected() -> None:
    state = create_world(42)
    bad = _StubPolicy(npc_id="00000000-0000-4000-8000-000000000999")
    fallback = _StubPolicy()

    command = decide_command(state, PROTAGONIST_ID, bad, fallback=fallback)

    assert fallback.calls == 1
    assert command is not None
    assert command.type == "start_cultivation"


def test_commands_are_deterministic_for_identical_proposals() -> None:
    first = create_world(42)
    second = create_world(42)
    first_command = decide_command(first, PROTAGONIST_ID, _StubPolicy())
    second_command = decide_command(second, PROTAGONIST_ID, _StubPolicy())

    assert first_command is not None
    assert second_command is not None
    assert first_command.command_id == second_command.command_id
    assert first_command.idempotency_key == second_command.idempotency_key


def test_proposal_rejection_carries_stable_code() -> None:
    state = create_world(42)
    policy = _StubPolicy(npc_id=PLAYER_ID)
    fallback = _StubPolicy(version_offset=1)

    with pytest.raises(ProposalRejected) as error:
        decide_command(state, PROTAGONIST_ID, policy, fallback=fallback)

    assert error.value.code == "stale_proposal"
    assert policy.calls == 1
    assert fallback.calls == 1