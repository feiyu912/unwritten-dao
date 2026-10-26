"""LLM-backed policy with strict parsing, one repair attempt, and audit records.

The policy never mutates world state. Invalid or malformed output is rejected;
``decide_command`` (in ``validator.py``) applies the deterministic UtilityPolicy
fallback exactly once.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agent_runtime.models import (
    ActionProposal,
    InferenceProvider,
    NpcObservation,
)
from agent_runtime.prompt import build_planning_prompt, repair_prompt
from agent_runtime.validator import ProposalRejected

_ID_NAMESPACE = uuid.UUID("7a41c2d9-0e58-4b3a-9f61-3d2c8e5b7a04")


class ProposalParseError(ValueError):
    """Model output could not be turned into a trustworthy proposal."""


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    npc_id: str
    tick: int
    world_version: int
    provider: str
    model_version: str
    system_prompt: str
    user_prompt: str
    raw_response: str | None
    attempts: int
    accepted: bool
    error: str | None
    latency_ms: float


@dataclass
class LLMPolicy:
    """Compose an inference provider into an ``AgentPolicy``."""

    provider: InferenceProvider
    model_version: str = "unknown"
    max_repair_attempts: int = 1
    records: list[DecisionRecord] = field(default_factory=list)

    def decide(self, observation: NpcObservation) -> ActionProposal:
        system, user = build_planning_prompt(observation)
        prompt = user
        attempts = 0
        last_error = ""
        max_attempts = 1 + max(0, self.max_repair_attempts)
        for attempt in range(max_attempts):
            attempts = attempt + 1
            started = time.perf_counter()
            try:
                raw = self.provider.complete(system=system, user=prompt)
            except Exception as exc:  # provider/network failure is not retryable here
                self._record(
                    observation,
                    decision_id=_decision_id(observation, attempt),
                    prompt=prompt,
                    raw=None,
                    attempts=attempts,
                    accepted=False,
                    error=f"provider_error: {exc}",
                    started=started,
                )
                raise ProposalRejected("llm_provider_error", str(exc)) from exc
            try:
                proposal = parse_proposal(raw, observation)
            except ProposalParseError as exc:
                last_error = str(exc)
                self._record(
                    observation,
                    decision_id=_decision_id(observation, attempt),
                    prompt=prompt,
                    raw=raw,
                    attempts=attempts,
                    accepted=False,
                    error=last_error,
                    started=started,
                )
                if attempt + 1 < max_attempts:
                    prompt = repair_prompt(user, last_error)
                    continue
                raise ProposalRejected("llm_invalid_output", last_error) from exc
            self._record(
                observation,
                decision_id=proposal.decision_id,
                prompt=prompt,
                raw=raw,
                attempts=attempts,
                accepted=True,
                error=None,
                started=started,
            )
            return proposal
        raise ProposalRejected("llm_invalid_output", last_error)

    def _record(
        self,
        observation: NpcObservation,
        *,
        decision_id: str,
        prompt: str,
        raw: str | None,
        attempts: int,
        accepted: bool,
        error: str | None,
        started: float,
    ) -> None:
        system, _ = build_planning_prompt(observation)
        self.records.append(
            DecisionRecord(
                decision_id=decision_id,
                npc_id=observation.npc_id,
                tick=observation.tick,
                world_version=observation.world_version,
                provider=type(self.provider).__name__,
                model_version=self.model_version,
                system_prompt=system,
                user_prompt=prompt,
                raw_response=raw,
                attempts=attempts,
                accepted=accepted,
                error=error,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        )


def parse_proposal(raw: str, observation: NpcObservation) -> ActionProposal:
    """Parse one model reply into a proposal bound to this observation."""
    if not isinstance(raw, str) or not raw.strip():
        raise ProposalParseError("empty response")
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ProposalParseError("response contains no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposalParseError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ProposalParseError("response JSON must be an object")

    intent = data.get("intent")
    if intent not in observation.available_actions:
        raise ProposalParseError(f"intent {intent!r} is not available")
    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ProposalParseError("arguments must be an object")
    decision_id = str(data.get("decision_id") or _decision_id(observation, 0))[:128]
    allowed_events = {
        memory.event_id for memory in observation.memories
    } | {event.event_id for event in observation.recent_events}
    memory_refs = [
        ref
        for ref in data.get("memory_refs", [])
        if isinstance(ref, int) and not isinstance(ref, bool) and ref in allowed_events
    ][:32]
    try:
        return ActionProposal(
            proposal_id=str(
                uuid.uuid5(
                    _ID_NAMESPACE,
                    f"{observation.npc_id}:{decision_id}:{observation.world_version}",
                )
            ),
            decision_id=decision_id,
            npc_id=observation.npc_id,
            observed_world_version=observation.world_version,
            goal_id=data.get("goal_id") or _active_goal(observation),
            intent=intent,
            arguments=arguments,
            valid_for_ticks=_clamp_int(data.get("valid_for_ticks", 7), 1, 3650),
            memory_refs=memory_refs,
            rationale_short=str(data.get("rationale_short") or "model proposal")[:500],
            confidence=_clamp_float(data.get("confidence", 0.5), 0.0, 1.0),
        )
    except ValidationError as exc:
        raise ProposalParseError(f"proposal failed validation: {exc.errors()[0]['msg']}") from exc


@dataclass
class ProposalReplayPolicy:
    """Replays recorded proposals without calling a model.

    Fixtures are consumed in order per ``(npc_id, tick)``. Missing fixtures are a
    hard error, never a silent fallback to a live provider.
    """

    proposals: Iterable[Mapping[str, Any]]
    _by_key: dict[tuple[str, int], deque[Mapping[str, Any]]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def __post_init__(self) -> None:
        for proposal in self.proposals:
            npc_id = str(proposal.get("npc_id", ""))
            tick = int(proposal.get("tick", -1))
            self._by_key[(npc_id, tick)].append(proposal)

    def decide(self, observation: NpcObservation) -> ActionProposal:
        queue = self._by_key.get((observation.npc_id, observation.tick))
        if not queue:
            raise ProposalRejected(
                "replay_fixture_missing",
                f"no recorded proposal for {observation.npc_id} at tick {observation.tick}",
            )
        fixture = queue.popleft()
        intent = fixture.get("intent")
        if intent not in observation.available_actions:
            raise ProposalRejected(
                "replay_intent_unavailable",
                f"recorded intent {intent!r} is not available now",
            )
        decision_id = str(fixture.get("decision_id") or _decision_id(observation, 0))[:128]
        return ActionProposal(
            proposal_id=str(
                uuid.uuid5(
                    _ID_NAMESPACE,
                    f"{observation.npc_id}:{decision_id}:{observation.world_version}",
                )
            ),
            decision_id=decision_id,
            npc_id=observation.npc_id,
            observed_world_version=observation.world_version,
            goal_id=fixture.get("goal_id") or _active_goal(observation),
            intent=intent,
            arguments=dict(fixture.get("arguments", {})),
            valid_for_ticks=int(fixture.get("valid_for_ticks", 7)),
            memory_refs=list(fixture.get("memory_refs", [])),
            rationale_short=str(fixture.get("rationale_short") or "replay")[:500],
            confidence=float(fixture.get("confidence", 0.5)),
        )


def _decision_id(observation: NpcObservation, attempt: int) -> str:
    return f"llm:{observation.npc_id}:{observation.tick}:{observation.world_version}:{attempt}"


def _active_goal(observation: NpcObservation) -> str | None:
    active = [goal for goal in observation.goals if goal.status == "active"]
    if not active:
        return None
    return sorted(active, key=lambda goal: (-goal.priority, goal.goal_id))[0].goal_id


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


__all__ = [
    "DecisionRecord",
    "LLMPolicy",
    "ProposalParseError",
    "ProposalReplayPolicy",
    "parse_proposal",
]