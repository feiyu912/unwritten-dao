"""Observation, proposal, and command plumbing for autonomous NPCs."""

from __future__ import annotations

from agent_runtime.dataset import (
    DecisionRecorder,
    DecisionSample,
    RecordingPolicy,
    write_jsonl,
)
from agent_runtime.decision import (
    ActionCandidate,
    CandidateGenerator,
    DecisionModel,
    DecisionModelPolicy,
    PolicyDecisionRecord,
    StrategicGoal,
    UtilityCandidateGenerator,
)
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
from agent_runtime.knowledge import (
    KnowledgeBoundaryError,
    KnowledgeViolation,
    NpcKnowledgeView,
    PrivateState,
    WorldFacts,
    explain_action,
    explain_event_chain,
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
    "ActionCandidate",
    "ActionProposal",
    "ActiveActionView",
    "AgentPolicy",
    "CandidateGenerator",
    "DecisionModel",
    "DecisionModelPolicy",
    "DecisionRecord",
    "DecisionRecorder",
    "DecisionSample",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "InMemoryEpisodeStore",
    "InferenceProvider",
    "KnowledgeBoundaryError",
    "KnowledgeViolation",
    "KnownLocation",
    "LLMPolicy",
    "MemoryEpisode",
    "MemoryRecord",
    "MemoryStore",
    "MockInferenceProvider",
    "NpcKnowledgeView",
    "NpcObservation",
    "ObservationSelf",
    "ObservedBelief",
    "ObservedGoal",
    "ObservedItem",
    "ObservedRelationship",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAICompatibleProvider",
    "PolicyDecisionRecord",
    "PrivateState",
    "ProposalIntent",
    "ProposalParseError",
    "ProposalRejected",
    "ProposalReplayPolicy",
    "ProviderError",
    "RecentEvent",
    "RecordingPolicy",
    "ReplayExhausted",
    "ReplayInferenceProvider",
    "RivalryPolicy",
    "StoryThread",
    "StrategicGoal",
    "UtilityCandidateGenerator",
    "UtilityPolicy",
    "VisibleNpc",
    "VisibleOpportunity",
    "WorldFacts",
    "build_observation",
    "build_planning_prompt",
    "cosine",
    "decide_and_apply",
    "decide_command",
    "explain_action",
    "explain_event_chain",
    "find_story_threads",
    "parse_proposal",
    "proposal_to_command",
    "repair_prompt",
    "score_memory",
    "write_jsonl",
]
