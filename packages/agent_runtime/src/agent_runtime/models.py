"""Pydantic mirrors of the cross-module agent contracts.

The authoritative shapes live in ``docs/contracts``:
``npc-observation.v1.schema.json`` and ``action-proposal.v1.schema.json``.
Nothing here may write world state; these are read-only views and intents.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

OBSERVATION_SCHEMA_VERSION: Literal["npc-observation.v1"] = "npc-observation.v1"
PROPOSAL_SCHEMA_VERSION: Literal["action-proposal.v1"] = "action-proposal.v1"

ProposalIntent = Literal[
    "wait",
    "move",
    "start_cultivation",
    "attempt_breakthrough",
    "transfer_item",
    "investigate",
    "enter_secret_realm",
    "claim_opportunity",
    "attack",
    "make_commitment",
]

PROPOSAL_INTENTS: tuple[ProposalIntent, ...] = (
    "wait",
    "move",
    "start_cultivation",
    "attempt_breakthrough",
    "transfer_item",
    "investigate",
    "enter_secret_realm",
    "claim_opportunity",
    "attack",
    "make_commitment",
)

GoalStatus = Literal["active", "achieved", "failed", "abandoned"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=False)


class ObservationSelf(StrictModel):
    name: str
    realm: int = Field(ge=0)
    stage: int = Field(ge=0)
    qi: int = Field(ge=0)
    foundation: float = Field(ge=0.0, le=1.0)
    health: float = Field(ge=0.0, le=1.0)
    wealth: int = Field(ge=0)
    lifespan_ticks: int = Field(ge=1)
    birth_tick: int
    estimated_remaining_life_ticks: int
    traits: dict[str, Any] = Field(default_factory=dict)


class ObservedItem(StrictModel):
    item_id: str
    name: str
    kind: str
    properties: dict[str, Any] = Field(default_factory=dict)


class VisibleOpportunity(StrictModel):
    opportunity_id: str
    name: str
    kind: str
    location_id: str
    active_until_tick: int = Field(ge=0)
    reward_item_ids: list[str] = Field(default_factory=list)


class VisibleNpc(StrictModel):
    npc_id: str
    name: str
    realm: int = Field(ge=0)
    stage: int = Field(ge=0)
    alive: bool


class ObservedRelationship(StrictModel):
    npc_id: str
    affinity: int
    trust: int
    fear: int
    respect: int
    debt: int


class ObservedBelief(StrictModel):
    subject_key: str
    predicate: str
    object_value: Any = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_event_id: int | None = Field(default=None, ge=1)


class KnownLocation(StrictModel):
    location_id: str
    name: str
    kind: str
    adjacent_ids: list[str] = Field(default_factory=list)


class MemoryRecord(StrictModel):
    event_id: int = Field(ge=1)
    tick: int = Field(ge=0)
    summary: str
    importance: float = Field(ge=0.0, le=1.0)
    emotional_valence: float = Field(ge=-1.0, le=1.0)


class RecentEvent(StrictModel):
    event_id: int = Field(ge=1)
    tick: int = Field(ge=0)
    type: str
    summary: str


class ObservedGoal(StrictModel):
    goal_id: str
    kind: str
    status: GoalStatus
    priority: float = Field(ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)


class ActiveActionView(StrictModel):
    type: str
    remaining_ticks: int = Field(ge=0)


class NpcObservation(StrictModel):
    """Everything one NPC can perceive or knows at a decision point."""

    schema_version: Literal["npc-observation.v1"] = OBSERVATION_SCHEMA_VERSION
    npc_id: str
    tick: int = Field(ge=0)
    world_version: int = Field(ge=0)
    location_id: str = Field(min_length=1)
    self: ObservationSelf
    inventory: list[ObservedItem] = Field(default_factory=list)
    visible_items: list[ObservedItem] = Field(default_factory=list)
    visible_opportunities: list[VisibleOpportunity] = Field(default_factory=list)
    visible_npcs: list[VisibleNpc] = Field(default_factory=list)
    relationships: list[ObservedRelationship] = Field(default_factory=list)
    beliefs: list[ObservedBelief] = Field(default_factory=list)
    known_locations: list[KnownLocation] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    recent_events: list[RecentEvent] = Field(default_factory=list)
    goals: list[ObservedGoal] = Field(default_factory=list)
    active_action: ActiveActionView | None = None
    available_actions: list[ProposalIntent] = Field(default_factory=list)

    @field_validator("available_actions")
    @classmethod
    def _unique_actions(cls, value: list[ProposalIntent]) -> list[ProposalIntent]:
        if len(set(value)) != len(value):
            raise ValueError("available_actions must not contain duplicates")
        return value


class ActionProposal(StrictModel):
    """What an agent wants to attempt. Never authoritative."""

    schema_version: Literal["action-proposal.v1"] = PROPOSAL_SCHEMA_VERSION
    proposal_id: str
    decision_id: str = Field(min_length=1, max_length=128)
    npc_id: str
    observed_world_version: int = Field(ge=0)
    goal_id: str | None = None
    intent: ProposalIntent
    arguments: dict[str, Any] = Field(default_factory=dict)
    valid_for_ticks: int = Field(default=7, ge=1, le=3650)
    memory_refs: list[int] = Field(default_factory=list, max_length=32)
    rationale_short: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("memory_refs")
    @classmethod
    def _positive_refs(cls, value: list[int]) -> list[int]:
        if any(ref < 1 for ref in value):
            raise ValueError("memory_refs must reference positive event ids")
        return value


@runtime_checkable
class AgentPolicy(Protocol):
    def decide(self, observation: NpcObservation) -> ActionProposal: ...


@runtime_checkable
class InferenceProvider(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


__all__ = [
    "OBSERVATION_SCHEMA_VERSION",
    "PROPOSAL_INTENTS",
    "PROPOSAL_SCHEMA_VERSION",
    "ActionProposal",
    "ActiveActionView",
    "AgentPolicy",
    "GoalStatus",
    "InferenceProvider",
    "KnownLocation",
    "MemoryRecord",
    "NpcObservation",
    "ObservationSelf",
    "ObservedBelief",
    "ObservedGoal",
    "ObservedItem",
    "ObservedRelationship",
    "ProposalIntent",
    "RecentEvent",
    "VisibleNpc",
    "VisibleOpportunity",
]
