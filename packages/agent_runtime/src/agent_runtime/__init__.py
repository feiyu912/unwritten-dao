"""Observation, proposal, and command plumbing for autonomous NPCs."""

from __future__ import annotations

from agent_runtime.inference import (
    MockInferenceProvider,
    ReplayExhausted,
    ReplayInferenceProvider,
)
from agent_runtime.llm import (
    DecisionRecord,
    LLMPolicy,
    ProposalParseError,
    ProposalReplayPolicy,
    parse_proposal,
)
from agent_runtime.models import (
    ActionProposal,
    ActiveActionView,
    AgentPolicy,
    InferenceProvider,
    KnownLocation,
    MemoryRecord,
    NpcObservation,
    ObservationSelf,
    ObservedBelief,
    ObservedGoal,
    ObservedItem,
    ObservedRelationship,
    ProposalIntent,
    RecentEvent,
    VisibleNpc,
    VisibleOpportunity,
)
from agent_runtime.observation import build_observation
from agent_runtime.policy import UtilityPolicy
from agent_runtime.prompt import build_planning_prompt, repair_prompt
from agent_runtime.validator import ProposalRejected, decide_command, proposal_to_command

__all__ = [
    "ActionProposal",
    "ActiveActionView",
    "AgentPolicy",
    "DecisionRecord",
    "InferenceProvider",
    "KnownLocation",
    "LLMPolicy",
    "MemoryRecord",
    "MockInferenceProvider",
    "NpcObservation",
    "ObservationSelf",
    "ObservedBelief",
    "ObservedGoal",
    "ObservedItem",
    "ObservedRelationship",
    "ProposalIntent",
    "ProposalParseError",
    "ProposalRejected",
    "ProposalReplayPolicy",
    "RecentEvent",
    "ReplayExhausted",
    "ReplayInferenceProvider",
    "UtilityPolicy",
    "VisibleNpc",
    "VisibleOpportunity",
    "build_observation",
    "build_planning_prompt",
    "decide_command",
    "parse_proposal",
    "proposal_to_command",
    "repair_prompt",
]