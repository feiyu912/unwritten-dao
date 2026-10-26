"""Observation, proposal, and command plumbing for autonomous NPCs."""

from __future__ import annotations

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
from agent_runtime.validator import ProposalRejected, decide_command, proposal_to_command

__all__ = [
    "ActionProposal",
    "ActiveActionView",
    "AgentPolicy",
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
    "ProposalRejected",
    "RecentEvent",
    "VisibleNpc",
    "VisibleOpportunity",
    "build_observation",
    "decide_command",
    "proposal_to_command",
]