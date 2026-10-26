#!/usr/bin/env python3
"""Collect decision samples for future BC / action scoring / RL.

    uv run python -m tools.collect_decisions --days 10 --policy utility

Each JSONL row contains the public observation, goals, available actions, the
proposed action, and whether the simulator accepted it. No state is written by
the recorder; proposals still go through world_core.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from agent_runtime.dataset import DecisionRecorder, RecordingPolicy, write_jsonl
from agent_runtime.validator import proposal_to_command

from agent_runtime import (
    LLMPolicy,
    MockInferenceProvider,
    ProposalRejected,
    RivalryPolicy,
    UtilityPolicy,
    build_observation,
)
from world_core import (
    PLAYER_ID,
    CommandRejected,
    advance_time,
    apply_command,
    create_world,
    state_checksum,
    validate_state,
)

MOCK_REPLY = json.dumps(
    {
        "intent": "start_cultivation",
        "arguments": {"days": 5},
        "valid_for_ticks": 7,
        "rationale_short": "dataset mock cultivation",
        "confidence": 0.4,
    }
)


def _policy(name: str, recorder: DecisionRecorder) -> RecordingPolicy:
    if name == "utility":
        base = UtilityPolicy()
    elif name == "rivalry":
        base = RivalryPolicy()
    elif name == "llm-mock":
        base = LLMPolicy(MockInferenceProvider(reply=MOCK_REPLY), model_version="mock-v1")
    else:
        raise ValueError(f"unknown policy {name}")
    return RecordingPolicy(base, recorder, name=name)


def collect(*, days: int, seed: int, policy_name: str) -> tuple[DecisionRecorder, Any]:
    state = create_world(seed)
    recorder = DecisionRecorder()
    policy = _policy(policy_name, recorder)
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive or npc.active_action is not None:
                continue
            observation = build_observation(state, npc.npc_id)
            try:
                proposal = policy.decide(observation)
            except ProposalRejected:
                continue
            sample = recorder.samples[-1]
            try:
                command = proposal_to_command(state, proposal)
                result = apply_command(state, command)
            except CommandRejected as exc:
                sample.outcome = "rejected"
                sample.rejection_code = exc.code
            except ProposalRejected as exc:
                sample.outcome = "rejected"
                sample.rejection_code = exc.code
            else:
                sample.outcome = "accepted"
                sample.result_event_ids = [event.event_id for event in result.events]
        advance_time(state, 1)
    return recorder, state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect decision samples.")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--policy", choices=["utility", "rivalry", "llm-mock"], default="utility")
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("reports/decisions_dataset.jsonl")
    )
    args = parser.parse_args(argv)

    recorder, state = collect(days=args.days, seed=args.seed, policy_name=args.policy)
    count = write_jsonl(args.out, recorder.samples)
    accepted = sum(1 for sample in recorder.samples if sample.outcome == "accepted")
    rejected = sum(1 for sample in recorder.samples if sample.outcome == "rejected")
    print(f"wrote {args.out} samples={count} accepted={accepted} rejected={rejected}")
    print(f"tick={state.tick} checksum={state_checksum(state)} violations={validate_state(state)}")
    return 0 if not validate_state(state) else 1


if __name__ == "__main__":
    sys.exit(main())
