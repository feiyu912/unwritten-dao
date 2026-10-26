"""Pluggable decision-model policy for future action scoring / BC / RL.

It does not train or call a model. A `DecisionModel` scores candidate actions;
the policy records the observation, strategic goal, candidates, mask, choice,
value estimate, and cited event ids for later dataset construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_runtime.models import ActionProposal, NpcObservation, ProposalIntent
from agent_runtime.policy import UtilityPolicy

_ID_NAMESPACE = uuid.UUID("f4b1c7d2-8a36-4d5e-9c71-2b8e6a0d3f95")


@dataclass(frozen=True)
class StrategicGoal:
    goal_id: str | None
    kind: str | None
    priority: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionCandidate:
    intent: ProposalIntent
    arguments: dict[str, Any]
    legal: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecisionRecord:
    decision_id: str
    npc_id: str
    tick: int
    world_version: int
    policy_name: str
    strategic_goal: StrategicGoal
    observation: dict[str, Any]
    candidates: tuple[dict[str, Any], ...]
    legal_intents: tuple[str, ...]
    chosen_intent: str
    chosen_arguments: dict[str, Any]
    value_estimate: float
    event_refs: tuple[int, ...]
    rationale: str
    fallback_used: bool


class DecisionModel(Protocol):
    def score(
        self, observation: NpcObservation, candidates: Sequence[ActionCandidate]
    ) -> Sequence[float]: ...

    def value(self, observation: NpcObservation) -> float: ...


class CandidateGenerator(Protocol):
    def generate(self, observation: NpcObservation) -> list[ActionCandidate]: ...


class UtilityCandidateGenerator:
    """Emits the utility proposal plus conservative wait/cultivate alternatives."""

    def __init__(self, fallback: UtilityPolicy | None = None) -> None:
        self._fallback = fallback or UtilityPolicy()

    def generate(self, observation: NpcObservation) -> list[ActionCandidate]:
        proposal = self._fallback.decide(observation)
        candidates = [
            ActionCandidate(
                intent=proposal.intent,
                arguments=dict(proposal.arguments),
                legal=proposal.intent in observation.available_actions,
                metadata={"source": "utility"},
            ),
            ActionCandidate(
                intent="wait",
                arguments={"ticks": 1},
                legal="wait" in observation.available_actions,
                metadata={"source": "conservative"},
            ),
            ActionCandidate(
                intent="start_cultivation",
                arguments={"days": 1},
                legal="start_cultivation" in observation.available_actions,
                metadata={"source": "conservative"},
            ),
        ]
        seen: set[tuple[str, str]] = set()
        unique: list[ActionCandidate] = []
        for candidate in candidates:
            key = (candidate.intent, repr(sorted(candidate.arguments.items())))
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique


class DecisionModelPolicy:
    """Selects a tactical action by scoring generated candidates."""

    def __init__(
        self,
        model: DecisionModel,
        *,
        generator: CandidateGenerator | None = None,
        fallback: UtilityPolicy | None = None,
        name: str = "decision_model",
    ) -> None:
        self.model = model
        self.generator = generator or UtilityCandidateGenerator(fallback)
        self.fallback = fallback or UtilityPolicy()
        self.name = name
        self.records: list[PolicyDecisionRecord] = []

    def decide(self, observation: NpcObservation) -> ActionProposal:
        goal = _strategic_goal(observation)
        candidates = self.generator.generate(observation)
        legal = [
            candidate
            for candidate in candidates
            if candidate.legal and candidate.intent in observation.available_actions
        ]
        if not legal:
            return self._fallback(observation, goal, candidates, reason="no_legal_candidates")

        try:
            scores = list(self.model.score(observation, candidates))
            value = float(self.model.value(observation))
        except Exception:
            return self._fallback(
                observation, goal, candidates, reason="model_error", score_error=True
            )
        if len(scores) != len(candidates):
            return self._fallback(observation, goal, candidates, reason="score_length_mismatch")

        masked = [
            score if candidate in legal else float("-inf")
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        best = max(range(len(candidates)), key=lambda index: masked[index])
        chosen = candidates[best]
        self._record(
            observation,
            goal,
            candidates,
            scores,
            legal,
            chosen,
            value,
            fallback_used=False,
            rationale=f"{self.name}: score {masked[best]:.4f}",
        )
        return _proposal_from(
            observation,
            goal,
            chosen,
            confidence=_confidence(masked[best]),
            rationale=f"{self.name}: score {masked[best]:.4f}",
        )

    def _fallback(
        self,
        observation: NpcObservation,
        goal: StrategicGoal,
        candidates: Sequence[ActionCandidate],
        *,
        reason: str,
        score_error: bool = False,
    ) -> ActionProposal:
        proposal = self.fallback.decide(observation)
        self._record(
            observation,
            goal,
            candidates,
            [0.0 for _ in candidates],
            [],
            ActionCandidate(
                proposal.intent,
                dict(proposal.arguments),
                True,
                {"source": "fallback"},
            ),
            0.0,
            fallback_used=True,
            rationale=f"fallback:{reason}",
        )
        return _proposal_from(
            observation,
            goal,
            ActionCandidate(proposal.intent, dict(proposal.arguments), True),
            confidence=0.3,
            rationale=f"fallback:{reason}",
        )

    def _record(
        self,
        observation: NpcObservation,
        goal: StrategicGoal,
        candidates: Sequence[ActionCandidate],
        scores: Sequence[float],
        legal: Sequence[ActionCandidate],
        chosen: ActionCandidate,
        value: float,
        *,
        fallback_used: bool,
        rationale: str,
    ) -> None:
        decision_id = f"dm:{observation.npc_id}:{observation.tick}:{observation.world_version}"
        legal_set = {(candidate.intent, repr(candidate.arguments)) for candidate in legal}
        candidate_rows = tuple(
            {
                "intent": candidate.intent,
                "arguments": dict(candidate.arguments),
                "legal": (candidate.intent, repr(candidate.arguments)) in legal_set,
                "score": float(scores[index]) if index < len(scores) else 0.0,
                "metadata": dict(candidate.metadata),
            }
            for index, candidate in enumerate(candidates)
        )
        event_refs = sorted(
            {memory.event_id for memory in observation.memories}
            | {event.event_id for event in observation.recent_events}
        )
        self.records.append(
            PolicyDecisionRecord(
                decision_id=decision_id,
                npc_id=observation.npc_id,
                tick=observation.tick,
                world_version=observation.world_version,
                policy_name=self.name,
                strategic_goal=goal,
                observation=observation.model_dump(mode="json"),
                candidates=candidate_rows,
                legal_intents=tuple(str(row["intent"]) for row in candidate_rows if row["legal"]),
                chosen_intent=chosen.intent,
                chosen_arguments=dict(chosen.arguments),
                value_estimate=round(value, 6),
                event_refs=tuple(event_refs),
                rationale=rationale,
                fallback_used=fallback_used,
            )
        )


def _strategic_goal(observation: NpcObservation) -> StrategicGoal:
    active = [goal for goal in observation.goals if goal.status == "active"]
    if not active:
        return StrategicGoal(None, None, 0.0)
    goal = sorted(active, key=lambda item: (-item.priority, item.goal_id))[0]
    return StrategicGoal(goal.goal_id, goal.kind, goal.priority, dict(goal.params))


def _proposal_from(
    observation: NpcObservation,
    goal: StrategicGoal,
    candidate: ActionCandidate,
    *,
    confidence: float,
    rationale: str,
) -> ActionProposal:
    decision_id = f"dm:{observation.npc_id}:{observation.tick}:{observation.world_version}"
    return ActionProposal(
        proposal_id=str(uuid.uuid5(_ID_NAMESPACE, decision_id)),
        decision_id=decision_id,
        npc_id=observation.npc_id,
        observed_world_version=observation.world_version,
        goal_id=goal.goal_id,
        intent=candidate.intent,
        arguments=dict(candidate.arguments),
        valid_for_ticks=7,
        memory_refs=[memory.event_id for memory in observation.memories[:5]],
        rationale_short=rationale[:500],
        confidence=confidence,
    )


def _confidence(score: float) -> float:
    if score == float("-inf"):
        return 0.0
    return round(max(0.0, min(1.0, score / (1.0 + abs(score)))), 6)


__all__ = [
    "ActionCandidate",
    "CandidateGenerator",
    "DecisionModel",
    "DecisionModelPolicy",
    "PolicyDecisionRecord",
    "StrategicGoal",
    "UtilityCandidateGenerator",
]
