#!/usr/bin/env python3
"""Record model proposals to fixtures, then replay the history without a model.

    uv run python -m tools.replay_decisions --days 30

Both runs use the same world and NPC ordering; the replay consumes recorded
proposals by (npc_id, tick) and must reproduce the identical checksum.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

from agent_runtime import (
    LLMPolicy,
    MockInferenceProvider,
    ProposalReplayPolicy,
    build_observation,
    proposal_to_command,
)
from world_core import (
    PLAYER_ID,
    WorldState,
    advance_time,
    apply_command,
    create_world,
    state_checksum,
    validate_state,
)

MOCK_REPLY = json.dumps(
    {
        "intent": "start_cultivation",
        "arguments": {"days": 30},
        "valid_for_ticks": 7,
        "rationale_short": "fixture cultivation",
        "confidence": 0.4,
    }
)


def _run(state: WorldState, *, days: int, policy: Any, record: list[dict[str, Any]] | None):
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive or npc.active_action is not None:
                continue
            observation = build_observation(state, npc.npc_id)
            proposal = policy.decide(observation)
            command = proposal_to_command(state, proposal)
            apply_command(state, command)
            if record is not None:
                record.append(
                    {
                        "tick": observation.tick,
                        "npc_id": proposal.npc_id,
                        "intent": proposal.intent,
                        "arguments": proposal.arguments,
                        "decision_id": proposal.decision_id,
                        "rationale_short": proposal.rationale_short,
                        "confidence": proposal.confidence,
                    }
                )
        advance_time(state, 1)


def record_and_replay(*, days: int, seed: int = 42) -> dict[str, object]:
    fixtures: list[dict[str, Any]] = []
    recorded = create_world(seed)
    _run(
        recorded,
        days=days,
        policy=LLMPolicy(MockInferenceProvider(reply=MOCK_REPLY), model_version="mock-v1"),
        record=fixtures,
    )

    replayed = create_world(seed)
    _run(replayed, days=days, policy=ProposalReplayPolicy(fixtures), record=None)

    return {
        "fixtures": len(fixtures),
        "recorded_checksum": state_checksum(recorded),
        "replayed_checksum": state_checksum(replayed),
        "tick": recorded.tick,
        "violations": validate_state(recorded) + validate_state(replayed),
        "fixtures_data": fixtures,
    }


def _write(path: pathlib.Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read(path: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record and replay model proposals.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("reports/decisions.jsonl"))
    parser.add_argument("--replay", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)

    if args.replay is not None:
        fixtures = _read(args.replay)
        state = create_world(args.seed)
        _run(state, days=args.days, policy=ProposalReplayPolicy(fixtures), record=None)
        print(f"replayed {len(fixtures)} fixtures → {state_checksum(state)}")
        return 0 if not validate_state(state) else 1

    report = record_and_replay(days=args.days, seed=args.seed)
    _write(args.out, report["fixtures_data"])  # type: ignore[arg-type]
    same = report["recorded_checksum"] == report["replayed_checksum"]
    print(f"fixtures={report['fixtures']} tick={report['tick']} out={args.out}")
    print(f"recorded={report['recorded_checksum']}")
    print(f"replayed={report['replayed_checksum']}")
    print(f"identical={same} violations={report['violations']}")
    return 0 if same and not report["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())