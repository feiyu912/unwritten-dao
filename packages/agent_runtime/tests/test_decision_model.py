from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_runtime.decision import (
    ActionCandidate,
    DecisionModelPolicy,
    UtilityCandidateGenerator,
)
from agent_runtime.models import NpcObservation
from agent_runtime.validator import proposal_to_command

from agent_runtime import build_observation, decide_command
from world_core import (
    LOC_BLACKWOOD_FOREST,
    PROTAGONIST_ID,
    apply_command,
    create_world,
    validate_state,
)


class _PreferCultivation:
    def score(
        self, observation: NpcObservation, candidates: Sequence[ActionCandidate]
    ) -> list[float]:
        return [
            10.0 if candidate.intent == "start_cultivation" else 0.0 for candidate in candidates
        ]

    def value(self, observation: NpcObservation) -> float:
        return 0.42


class _IllegalHighScore:
    def score(
        self, observation: NpcObservation, candidates: Sequence[ActionCandidate]
    ) -> list[float]:
        return [100.0 if candidate.intent == "attack" else 0.0 for candidate in candidates]

    def value(self, observation: NpcObservation) -> float:
        return -1.0


class _BrokenModel:
    def score(
        self, observation: NpcObservation, candidates: Sequence[ActionCandidate]
    ) -> list[float]:
        raise RuntimeError("boom")

    def value(self, observation: NpcObservation) -> float:
        return 0.0


class _AttackOnlyGenerator:
    def generate(self, observation: NpcObservation) -> list[ActionCandidate]:
        return [
            ActionCandidate(
                intent="attack",
                arguments={"target_id": observation.npc_id, "intent": "kill"},
                legal=False,
            )
        ]


class _MixedGenerator:
    def generate(self, observation: NpcObservation) -> list[ActionCandidate]:
        return [
            ActionCandidate(
                intent="attack",
                arguments={"target_id": observation.npc_id, "intent": "kill"},
                legal=False,
            ),
            ActionCandidate(intent="wait", arguments={"ticks": 1}, legal=True),
        ]


def _observation():
    state = create_world(42)
    return state, build_observation(state, PROTAGONIST_ID)


def test_decision_model_selects_scored_candidate_and_records() -> None:
    state, observation = _observation()
    policy = DecisionModelPolicy(_PreferCultivation())
    proposal = policy.decide(observation)

    assert proposal.intent == "start_cultivation"
    assert proposal.goal_id == "goal_breakthrough"
    assert policy.records
    record = policy.records[-1]
    assert record.chosen_intent == "start_cultivation"
    assert record.value_estimate == 0.42
    assert record.strategic_goal.kind == "breakthrough"
    assert record.candidates
    assert record.legal_intents
    assert "start_cultivation" in record.legal_intents
    assert record.observation["npc_id"] == PROTAGONIST_ID
    assert "location_ancient_cave" not in str(record.observation)
    assert "item_foundation_pill" not in str(record.observation)
    assert record.event_refs == tuple(
        sorted(
            {memory.event_id for memory in observation.memories}
            | {event.event_id for event in observation.recent_events}
        )
    )
    assert record.fallback_used is False

    command = proposal_to_command(state, proposal)
    apply_command(state, command)
    assert validate_state(state) == []


def test_illegal_high_score_is_masked() -> None:
    _, observation = _observation()
    policy = DecisionModelPolicy(_IllegalHighScore(), generator=_MixedGenerator())
    proposal = policy.decide(observation)
    assert proposal.intent == "wait"
    record = policy.records[-1]
    attack = next(row for row in record.candidates if row["intent"] == "attack")
    assert attack["legal"] is False
    assert attack["score"] == 100.0


def test_all_masked_candidates_fall_back_to_utility() -> None:
    _, observation = _observation()
    policy = DecisionModelPolicy(_IllegalHighScore(), generator=_AttackOnlyGenerator())
    proposal = policy.decide(observation)
    assert proposal.intent == "move"
    assert proposal.arguments["to_location_id"] == LOC_BLACKWOOD_FOREST
    record = policy.records[-1]
    assert record.fallback_used is True
    assert record.chosen_intent == "move"


def test_model_error_falls_back_and_is_recorded() -> None:
    _, observation = _observation()
    policy = DecisionModelPolicy(_BrokenModel())
    proposal = policy.decide(observation)
    assert proposal.intent in observation.available_actions
    assert policy.records[-1].fallback_used is True


def test_decision_model_is_deterministic() -> None:
    _, observation = _observation()
    first = DecisionModelPolicy(_PreferCultivation()).decide(observation)
    second = DecisionModelPolicy(_PreferCultivation()).decide(observation)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_utility_generator_produces_stable_unique_candidates() -> None:
    _, observation = _observation()
    generator = UtilityCandidateGenerator()
    candidates = generator.generate(observation)
    assert len(candidates) >= 2
    keys = {(candidate.intent, repr(candidate.arguments)) for candidate in candidates}
    assert len(keys) == len(candidates)
    assert any(candidate.metadata.get("source") == "utility" for candidate in candidates)


def test_record_is_json_serializable_for_future_datasets() -> None:
    _, observation = _observation()
    policy = DecisionModelPolicy(_PreferCultivation())
    policy.decide(observation)
    record = policy.records[-1]
    import json

    payload: dict[str, Any] = {
        "observation": record.observation,
        "candidates": list(record.candidates),
        "chosen": {"intent": record.chosen_intent, "arguments": record.chosen_arguments},
        "event_refs": list(record.event_refs),
    }
    json.dumps(payload, ensure_ascii=False)


def test_decision_model_policy_is_usable_as_agent_policy() -> None:
    state, _ = _observation()
    policy = DecisionModelPolicy(_PreferCultivation())
    command = decide_command(state, PROTAGONIST_ID, policy)
    assert command is not None
    apply_command(state, command)
    assert state.npcs[PROTAGONIST_ID].active_action is not None
