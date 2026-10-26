"""Observation, proposal, and command plumbing for autonomous NPCs."""

from __future__ import annotations

from agent_runtime.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    cosine,
)
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
from agent_runtime.memory import (
    InMemoryEpisodeStore,
    MemoryEpisode,
    MemoryStore,
    score_memory,
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
from agent_runtime.narrative import IMPORTANCE, StoryThread, find_story_threads
from agent_runtime.observation import build_observation
from agent_runtime.policy import RivalryPolicy, UtilityPolicy
from agent_runtime.prompt import build_planning_prompt, repair_prompt
from agent_runtime.providers import OpenAICompatibleProvider, ProviderError
from agent_runtime.validator import (
    ProposalRejected,
    decide_and_apply,
    decide_command,
    proposal_to_command,
)

__all__ = [
    "IMPORTANCE",
    "ActionProposal",
    "ActiveActionView",
    "AgentPolicy",
    "DecisionRecord",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "InMemoryEpisodeStore",
    "InferenceProvider",
    "KnownLocation",
    "LLMPolicy",
    "MemoryEpisode",
    "MemoryRecord",
    "MemoryStore",
    "MockInferenceProvider",
    "NpcObservation",
    "ObservationSelf",
    "ObservedBelief",
    "ObservedGoal",
    "ObservedItem",
    "ObservedRelationship",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAICompatibleProvider",
    "ProposalIntent",
    "ProposalParseError",
    "ProposalRejected",
    "ProposalReplayPolicy",
    "ProviderError",
    "RecentEvent",
    "ReplayExhausted",
    "ReplayInferenceProvider",
    "RivalryPolicy",
    "StoryThread",
    "UtilityPolicy",
    "VisibleNpc",
    "VisibleOpportunity",
    "build_observation",
    "build_planning_prompt",
    "cosine",
    "decide_and_apply",
    "decide_command",
    "find_story_threads",
    "parse_proposal",
    "proposal_to_command",
    "repair_prompt",
    "score_memory",
]
