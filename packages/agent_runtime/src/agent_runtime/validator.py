"""Validate agent proposals and convert them into authoritative commands.

Validation here is intentionally shallow: it rejects proposals that cannot be
trusted to belong to this decision (wrong NPC, stale world version, unknown or
unavailable intent). The simulator still performs all legality checks.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from world_core.commands import CommandResult, WorldCommand, make_command
from world_core.models import WorldState

from agent_runtime.models import (
    PROPOSAL_INTENTS,
    ActionProposal,
    AgentPolicy,
    NpcObservation,
)
from agent_runtime.observation import build_observation
from agent_runtime.policy import UtilityPolicy
from world_core import CommandRejected, apply_command

_ID_NAMESPACE = uuid.UUID("2d3f7e6a-9b41-4c58-8f0d-6a1e5c7b9d20")


class ProposalRejected(Exception):
    """A proposal is not trustworthy for this state; try the fallback once."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def proposal_to_command(state: WorldState, proposal: ActionProposal) -> WorldCommand:
    """Convert a validated proposal into a deterministic ``WorldCommand``."""
    if proposal.npc_id not in state.npcs:
        raise ProposalRejected("wrong_npc", f"unknown npc {proposal.npc_id}")
    if proposal.observed_world_version != state.state_version:
        raise ProposalRejected(
            "stale_proposal",
            "proposal was made against an older world version",
        )
    if proposal.intent not in PROPOSAL_INTENTS:
        raise ProposalRejected("unknown_intent", f"unsupported intent {proposal.intent}")

    key = _idempotency_key(state, proposal)
    command_id = str(uuid.uuid5(_ID_NAMESPACE, f"command:{key}"))
    return make_command(
        state,
        proposal.npc_id,
        proposal.intent,
        dict(proposal.arguments),
        source="agent",
        idempotency_key=key,
        command_id=command_id,
    )


def decide_command(
    state: WorldState,
    npc_id: str,
    policy: AgentPolicy,
    *,
    fallback: AgentPolicy | None = None,
    memories: Sequence[Mapping[str, Any]] = (),
    recent_events: Sequence[Mapping[str, Any]] = (),
) -> WorldCommand | None:
    """Ask ``policy`` for a proposal and return a legal command (or ``None``).

    Dead or busy NPCs are skipped without calling the policy. A rejected
    proposal triggers exactly one deterministic fallback attempt.
    """
    npc = state.npcs.get(npc_id)
    if npc is None:
        raise ProposalRejected("wrong_npc", f"unknown npc {npc_id}")
    if not npc.alive or npc.active_action is not None:
        return None

    observation = build_observation(state, npc_id, memories=memories, recent_events=recent_events)
    try:
        proposal = policy.decide(observation)
        return _command_for(state, npc_id, observation, proposal)
    except ProposalRejected:
        fallback_policy = fallback if fallback is not None else _default_fallback()
        fallback_proposal = fallback_policy.decide(observation)
        return _command_for(state, npc_id, observation, fallback_proposal)


def _default_fallback() -> AgentPolicy:
    return UtilityPolicy()


def _command_for(
    state: WorldState,
    npc_id: str,
    observation: NpcObservation,
    proposal: ActionProposal,
) -> WorldCommand:
    if proposal.npc_id != npc_id:
        raise ProposalRejected(
            "wrong_npc",
            f"proposal targets {proposal.npc_id}, expected {npc_id}",
        )
    if proposal.intent not in observation.available_actions:
        raise ProposalRejected(
            "intent_unavailable",
            f"{proposal.intent} is not available to {npc_id} right now",
        )
    return proposal_to_command(state, proposal)


def _idempotency_key(state: WorldState, proposal: ActionProposal) -> str:
    arguments = json.dumps(
        proposal.arguments,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    material = f"{proposal.decision_id}|{proposal.intent}|{arguments}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    key = f"agent:{proposal.npc_id}:{proposal.intent}:{state.state_version}:{digest}"
    return key[:128]


def decide_and_apply(
    state: WorldState,
    npc_id: str,
    policy: AgentPolicy,
    *,
    fallback: AgentPolicy | None = None,
    memories: Sequence[Mapping[str, Any]] = (),
    recent_events: Sequence[Mapping[str, Any]] = (),
) -> CommandResult | None:
    """Decide, apply through the simulator, and fall back once if it rejects.

    This is the full safety chain: proposal validation catches stale/identity
    errors, and the simulator catches impossible plans. The fallback is always
    the deterministic UtilityPolicy.
    """
    command = decide_command(
        state,
        npc_id,
        policy,
        memories=memories,
        recent_events=recent_events,
    )
    if command is None:
        return None
    try:
        return apply_command(state, command)
    except CommandRejected as first_error:
        fallback_policy = fallback if fallback is not None else _default_fallback()
        fallback_command = decide_command(
            state,
            npc_id,
            fallback_policy,
            memories=memories,
            recent_events=recent_events,
        )
        if fallback_command is None:
            raise
        try:
            return apply_command(state, fallback_command)
        except CommandRejected as second_error:
            raise RuntimeError(
                f"fallback command rejected after {first_error.code}: {second_error.code}"
            ) from second_error


__all__ = [
    "ProposalRejected",
    "decide_and_apply",
    "decide_command",
    "proposal_to_command",
]
