"""Select the agent policy for a decision from environment settings.

Only the six major roles use the LLM path; background NPCs stay on the
deterministic utility policy (matching the MVP's tiered agent design).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from world_core.models import Npc

from agent_runtime import (
    AgentPolicy,
    DecisionModelPolicy,
    LLMPolicy,
    MockInferenceProvider,
    OpenAICompatibleProvider,
    RivalryPolicy,
    UtilityPolicy,
    UtilityScoringModel,
)

MAJOR_ROLES = frozenset(
    {"player", "protagonist", "sect_leader", "enemy_leader", "alchemist_elder", "rival"}
)

_MOCK_REPLY = json.dumps(
    {
        "decision_id": "server-mock",
        "intent": "start_cultivation",
        "arguments": {"days": 30},
        "valid_for_ticks": 7,
        "rationale_short": "由本地 mock 模型决定的稳健修炼。",
        "confidence": 0.3,
    },
    ensure_ascii=False,
)


@dataclass(frozen=True)
class PolicySelection:
    mode: str
    policy: AgentPolicy


def is_major(npc: Npc) -> bool:
    return npc.canonical_role in MAJOR_ROLES


def policy_for(npc: Npc) -> PolicySelection:
    if not is_major(npc):
        return PolicySelection("utility", UtilityPolicy())
    return build_policy()


def build_policy() -> PolicySelection:
    mode = os.environ.get("AGENT_PROVIDER", "utility").strip().lower()
    if mode in {"llm-mock", "llm_mock"}:
        reply = os.environ.get("LLM_MOCK_REPLY") or _MOCK_REPLY
        return PolicySelection(
            "llm-mock",
            LLMPolicy(MockInferenceProvider(reply=reply), model_version="mock-v1"),
        )
    if mode in {"decision-model", "decision_model"}:
        return PolicySelection(
            "decision-model",
            DecisionModelPolicy(UtilityScoringModel(), name="utility-scoring"),
        )
    if mode == "openai":
        base_url = os.environ.get("LLM_BASE_URL")
        model = os.environ.get("LLM_MODEL")
        if not base_url or not model:
            raise RuntimeError("AGENT_PROVIDER=openai requires LLM_BASE_URL and LLM_MODEL")
        return PolicySelection(
            "openai",
            LLMPolicy(
                OpenAICompatibleProvider(
                    base_url=base_url,
                    model=model,
                    api_key=os.environ.get("LLM_API_KEY"),
                    timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
                ),
                model_version=os.environ.get("LLM_MODEL_VERSION", model),
            ),
        )
    return PolicySelection("utility", RivalryPolicy())


__all__ = ["MAJOR_ROLES", "PolicySelection", "build_policy", "is_major", "policy_for"]
