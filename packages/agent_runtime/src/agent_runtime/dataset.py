"""Decision dataset recording for future behavior cloning / RL.

Records the public observation, available actions, chosen proposal, and the
simulator outcome. It never mutates state and never stores a model's private
chain of thought.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from agent_runtime.models import ActionProposal, AgentPolicy, NpcObservation

_NAMESPACE = uuid.UUID("9c4e2a71-5b08-4d3f-a6e2-71f0c8b4d953")


@dataclass
class DecisionSample:
    schema_version: str
    decision_id: str
    policy: str
    npc_id: str
    tick: int
    world_version: int
    observation: dict[str, Any]
    goals: list[dict[str, Any]]
    available_actions: list[str]
    chosen_intent: str
    chosen_arguments: dict[str, Any]
    rationale_short: str
    confidence: float
    event_refs: list[int] = field(default_factory=list)
    outcome: str | None = None
    rejection_code: str | None = None
    result_event_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionRecorder:
    def __init__(self) -> None:
        self.samples: list[DecisionSample] = []

    def make_sample(
        self, observation: NpcObservation, proposal: ActionProposal, *, policy: str
    ) -> DecisionSample:
        decision_id = str(
            uuid.uuid5(
                _NAMESPACE,
                f"{policy}:{proposal.npc_id}:{observation.tick}:{observation.world_version}",
            )
        )
        event_refs = sorted(
            {memory.event_id for memory in observation.memories}
            | {event.event_id for event in observation.recent_events}
        )
        sample = DecisionSample(
            schema_version="decision-sample.v1",
            decision_id=decision_id,
            policy=policy,
            npc_id=proposal.npc_id,
            tick=observation.tick,
            world_version=observation.world_version,
            observation=observation.model_dump(mode="json"),
            goals=[goal.model_dump(mode="json") for goal in observation.goals],
            available_actions=list(observation.available_actions),
            chosen_intent=proposal.intent,
            chosen_arguments=dict(proposal.arguments),
            rationale_short=proposal.rationale_short,
            confidence=proposal.confidence,
            event_refs=event_refs,
        )
        self.samples.append(sample)
        return sample


class RecordingPolicy:
    """Wraps any policy and records each proposal before returning it."""

    def __init__(self, policy: AgentPolicy, recorder: DecisionRecorder, *, name: str) -> None:
        self.policy = policy
        self.recorder = recorder
        self.name = name

    def decide(self, observation: NpcObservation) -> ActionProposal:
        proposal = self.policy.decide(observation)
        self.recorder.make_sample(observation, proposal, policy=self.name)
        return proposal


def write_jsonl(path: pathlib.Path, samples: Iterable[DecisionSample]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


__all__ = ["DecisionRecorder", "DecisionSample", "RecordingPolicy", "write_jsonl"]
