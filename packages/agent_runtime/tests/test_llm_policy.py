from __future__ import annotations

import json

import pytest

from agent_runtime import (
    DecisionRecord,
    LLMPolicy,
    MockInferenceProvider,
    ProposalRejected,
    ProposalReplayPolicy,
    ReplayInferenceProvider,
    UtilityPolicy,
    build_observation,
    build_planning_prompt,
    decide_command,
)
from world_core import (
    LOC_BLACKWOOD_FOREST,
    PROTAGONIST_ID,
    apply_command,
    create_world,
)


class _FailingProvider:
    name = "failing"

    def complete(self, *, system: str, user: str) -> str:
        raise RuntimeError("network down")


def _reply(**overrides: object) -> str:
    payload: dict[str, object] = {
        "decision_id": "llm-decision-1",
        "npc_id": "wrong-npc",
        "observed_world_version": 999,
        "intent": "move",
        "arguments": {"to_location_id": LOC_BLACKWOOD_FOREST},
        "valid_for_ticks": 7,
        "memory_refs": [999999],
        "rationale_short": "先去林中寻找线索。",
        "confidence": 0.7,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_prompt_separates_facts_and_hides_secret_interior() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    system, user = build_planning_prompt(observation)

    assert "WORLD_FACTS" in user
    assert "BELIEFS" in user
    assert "AVAILABLE_ACTIONS" in user
    assert "action-proposal.v1" in system
    assert "location_ancient_cave" not in user
    assert "item_foundation_pill" not in user
    assert PROTAGONIST_ID in user


def test_llm_policy_forces_identity_and_accepts_valid_output() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = LLMPolicy(MockInferenceProvider(reply=_reply()), model_version="mock-v1")
    proposal = policy.decide(observation)

    assert proposal.npc_id == observation.npc_id
    assert proposal.observed_world_version == observation.world_version
    assert proposal.intent == "move"
    assert proposal.arguments == {"to_location_id": LOC_BLACKWOOD_FOREST}
    assert proposal.memory_refs == []  # unknown event ids are dropped
    assert len(policy.records) == 1
    record = policy.records[0]
    assert isinstance(record, DecisionRecord)
    assert record.accepted is True
    assert record.model_version == "mock-v1"


def test_llm_policy_repairs_once_then_accepts() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    provider = ReplayInferenceProvider(replies=["not json", _reply()])
    policy = LLMPolicy(provider)

    proposal = policy.decide(observation)
    assert proposal.intent == "move"
    assert provider.index == 2
    assert len(policy.records) == 2
    assert policy.records[0].accepted is False
    assert policy.records[1].accepted is True
    assert "PREVIOUS_OUTPUT_INVALID" in policy.records[1].user_prompt


def test_llm_policy_gives_up_after_one_repair() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = LLMPolicy(ReplayInferenceProvider(replies=["nope", "still nope"]))

    with pytest.raises(ProposalRejected) as error:
        policy.decide(observation)
    assert error.value.code == "llm_invalid_output"
    assert len(policy.records) == 2
    assert all(not record.accepted for record in policy.records)


def test_unknown_intent_is_rejected() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = LLMPolicy(MockInferenceProvider(reply=_reply(intent="fly")))

    with pytest.raises(ProposalRejected) as error:
        policy.decide(observation)
    assert error.value.code == "llm_invalid_output"


def test_provider_error_is_wrapped() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = LLMPolicy(_FailingProvider())  # type: ignore[arg-type]

    with pytest.raises(ProposalRejected) as error:
        policy.decide(observation)
    assert error.value.code == "llm_provider_error"
    assert len(policy.records) == 1
    assert "network down" in (policy.records[0].error or "")


def test_invalid_llm_falls_back_to_utility_policy() -> None:
    state = create_world(42)
    policy = LLMPolicy(MockInferenceProvider(reply="{}"))
    command = decide_command(state, PROTAGONIST_ID, policy)

    assert command is not None
    assert command.actor_id == PROTAGONIST_ID
    apply_command(state, command)


def test_proposal_replay_policy_consumes_fixtures() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    fixtures = [
        {
            "npc_id": PROTAGONIST_ID,
            "tick": observation.tick,
            "intent": "move",
            "arguments": {"to_location_id": LOC_BLACKWOOD_FOREST},
            "rationale_short": "replayed",
        }
    ]
    policy = ProposalReplayPolicy(fixtures)
    proposal = policy.decide(observation)
    assert proposal.intent == "move"

    with pytest.raises(ProposalRejected) as error:
        policy.decide(observation)
    assert error.value.code == "replay_fixture_missing"


def test_replay_policy_works_through_decide_command() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    policy = ProposalReplayPolicy(
        [
            {
                "npc_id": PROTAGONIST_ID,
                "tick": observation.tick,
                "intent": "move",
                "arguments": {"to_location_id": LOC_BLACKWOOD_FOREST},
            }
        ]
    )
    command = decide_command(state, PROTAGONIST_ID, policy)
    assert command is not None
    apply_command(state, command)
    assert state.npcs[PROTAGONIST_ID].location_id == LOC_BLACKWOOD_FOREST


def test_utility_policy_still_available_as_explicit_fallback() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    proposal = UtilityPolicy().decide(observation)
    assert proposal.intent in observation.available_actions
