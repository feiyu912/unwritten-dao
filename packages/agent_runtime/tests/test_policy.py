from __future__ import annotations

import pytest

from agent_runtime import (
    ActionProposal,
    MockInferenceProvider,
    ProposalRejected,
    ReplayExhausted,
    ReplayInferenceProvider,
    UtilityPolicy,
    build_observation,
    decide_command,
)
from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    OPP_FOUNDATION_PILL,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    advance_time,
    apply_command,
    create_world,
    validate_state,
)


class _WrongNpcPolicy:
    def decide(self, observation):  # type: ignore[no-untyped-def]
        return ActionProposal(
            proposal_id="00000000-0000-4000-8000-000000000001",
            decision_id="wrong-npc",
            npc_id="00000000-0000-4000-8000-000000000002",
            observed_world_version=observation.world_version,
            intent="wait",
            arguments={"ticks": 1},
            valid_for_ticks=7,
            memory_refs=[],
            rationale_short="deliberately wrong",
            confidence=0.1,
        )


def test_utility_policy_drives_the_protagonist_to_the_pill() -> None:
    state = create_world(42)
    event_types: list[str] = []
    for _day in range(400):
        command = decide_command(state, PROTAGONIST_ID, UtilityPolicy())
        if command is not None:
            event_types.extend(event.type for event in apply_command(state, command).events)
        advance_time(state, 1)
        if "BREAKTHROUGH_ATTEMPT" in event_types:
            break

    protagonist = state.npcs[PROTAGONIST_ID]
    assert ITEM_MAP_FRAGMENT in protagonist.inventory
    assert protagonist.npc_id in state.secret_realms[REALM_ANCIENT_CAVE].discovered_by
    assert "OPPORTUNITY_CLAIMED" in event_types
    assert "BREAKTHROUGH_ATTEMPT" in event_types
    assert state.opportunities[OPP_FOUNDATION_PILL].claimed_by == protagonist.npc_id
    assert validate_state(state) == []


def test_observation_does_not_leak_the_secret_interior() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    known_ids = {location.location_id for location in observation.known_locations}

    assert LOC_ANCIENT_CAVE not in known_ids
    assert all(LOC_ANCIENT_CAVE not in loc.adjacent_ids for loc in observation.known_locations)
    assert all(item.item_id != "item_foundation_pill" for item in observation.visible_items)


def test_rejected_proposal_uses_exactly_one_fallback() -> None:
    state = create_world(42)
    command = decide_command(state, PROTAGONIST_ID, _WrongNpcPolicy())
    assert command is not None
    assert command.actor_id == PROTAGONIST_ID
    apply_command(state, command)
    assert validate_state(state) == []


def test_decide_command_skips_busy_npc() -> None:
    state = create_world(42)
    from world_core import make_command

    busy = make_command(
        state,
        PROTAGONIST_ID,
        "start_cultivation",
        {"days": 10},
        source="test",
    )
    apply_command(state, busy)
    assert decide_command(state, PROTAGONIST_ID, UtilityPolicy()) is None


def test_mock_and_replay_providers() -> None:
    mock = MockInferenceProvider()
    first = mock.complete(system="s", user="u")
    second = mock.complete(system="s", user="u")
    assert first == second
    assert len(mock.calls) == 2

    replay = ReplayInferenceProvider(replies=['{"intent":"wait"}', '{"intent":"wait"}'])
    assert replay.complete(system="s", user="u") == '{"intent":"wait"}'
    assert replay.complete(system="s", user="u") == '{"intent":"wait"}'
    with pytest.raises(ReplayExhausted):
        replay.complete(system="s", user="u")


def test_utility_policy_is_deterministic() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = UtilityPolicy()
    first = policy.decide(observation)
    second = policy.decide(observation)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_stale_proposal_is_rejected_before_simulation() -> None:
    state = create_world(42)
    advance_time(state, 1)
    observation = build_observation(state, PROTAGONIST_ID)
    proposal = ActionProposal(
        proposal_id="00000000-0000-4000-8000-000000000003",
        decision_id="stale",
        npc_id=PROTAGONIST_ID,
        observed_world_version=observation.world_version - 1,
        intent="wait",
        arguments={"ticks": 1},
        valid_for_ticks=7,
        memory_refs=[],
        rationale_short="stale proposal",
        confidence=0.1,
    )
    from agent_runtime.validator import proposal_to_command

    with pytest.raises(ProposalRejected) as error:
        proposal_to_command(state, proposal)
    assert error.value.code == "stale_proposal"